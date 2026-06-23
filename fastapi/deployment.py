"""DIEP Phase 24 — Production Cutover Automation.

A deployment orchestration and verification framework that executes and validates
MW2 production-cutover activities. It is built ON TOP of the MW2 readiness engine
(readiness.py): pre-cutover validation reuses the scored readiness assessment and
container inspection, and adds cutover-specific probes (DB backups, MinIO archive),
while post-cutover validation verifies the full live surface (FastAPI, portal,
Redis, Kafka, Prometheus, Grafana).

PRODUCTION-SAFE BY CONSTRUCTION: every infrastructure interaction here is a
READ-ONLY probe (HTTP GET, `docker inspect`, a Redis PING, a directory listing).
The "cutover execution workflow" does NOT restart services, run migrations, or
mutate any live component — it generates the deployment record, captures a
read-only baseline snapshot, records operator-attested checklist actions, runs the
validations, and persists the evidence + an append-only audit trail. The only
writes this module performs are to its own additive evidence tables
(platform_deployment_runs / platform_deployment_events) and to Prometheus gauges.

Pure-dict/pydantic surface; reuses common.py DB helpers. Read-only against infra.
"""
from __future__ import annotations

import os
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from prometheus_client import Gauge
from pydantic import BaseModel, Field

import common
import readiness as readiness_service

CheckStatus = Literal["PASS", "WARN", "FAIL"]
ValidationStatus = Literal["PASS", "FAIL"]
RunStatus = Literal["STARTED", "VALIDATED", "FAILED", "ROLLED_BACK"]
GateStatus = Literal["IN_PROGRESS", "GO", "NO_GO"]

PRE_CUTOVER_CHECK_NAMES = (
    "mw2_readiness_certification",
    "critical_containers_healthy",
    "database_backups_present",
    "minio_archive_accessible",
    "kafka_health",
    "redis_health",
)
POST_CUTOVER_CHECK_NAMES = (
    "fastapi_readyz",
    "portal_login",
    "redis_connectivity",
    "kafka_metrics",
    "prometheus_targets",
    "grafana_availability",
)


# --- models ------------------------------------------------------------------
class DeploymentCheckResult(BaseModel):
    check_name: str
    status: CheckStatus
    weight: int
    score: int
    critical: bool = True
    message: str
    observed: dict[str, Any] = Field(default_factory=dict)
    threshold: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    phase: Literal["pre_cutover", "post_cutover"]
    status: ValidationStatus
    score: int = Field(ge=0, le=100)
    pass_threshold: int = Field(ge=0, le=100)
    checked_at: datetime
    checks: list[DeploymentCheckResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class DeploymentEvent(BaseModel):
    recorded_at: datetime
    event_type: str
    actor: str
    detail: dict[str, Any] = Field(default_factory=dict)


class DeploymentSummary(BaseModel):
    deployment_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: RunStatus
    deployment_status: GateStatus
    operator: str
    change_ref: str | None = None
    validation_score: int | None = None
    pass_threshold: int
    duration_seconds: float | None = None


class DeploymentRecord(DeploymentSummary):
    readiness_run_id: str | None = None
    baseline: dict[str, Any] = Field(default_factory=dict)
    pre_cutover: dict[str, Any] = Field(default_factory=dict)
    post_cutover: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    source: str = "api"
    tenant_id: str = "default"
    events: list[DeploymentEvent] = Field(default_factory=list)


class DeploymentHistoryResponse(BaseModel):
    total: int
    limit: int
    since_hours: int
    status: RunStatus | None = None
    runs: list[DeploymentSummary] = Field(default_factory=list)


class DeploymentStatusResponse(BaseModel):
    latest: DeploymentRecord | None = None
    pre_cutover_now: ValidationResult | None = None


# --- config ------------------------------------------------------------------
@dataclass
class DeploymentConfig:
    pass_threshold: int
    critical_containers: tuple[str, ...]
    fastapi_readyz_url: str
    portal_url: str
    minio_health_url: str
    prometheus_url: str
    grafana_url: str
    kafka_exporter_url: str
    redis_host: str
    redis_port: int
    redis_password: str | None
    backup_dir: str
    backup_globs: tuple[str, ...]
    backup_max_age_hours: float
    source: str
    tenant_id: str
    http_timeout_seconds: float = 5.0
    connect_timeout_seconds: float = 3.0


def load_deployment_config() -> DeploymentConfig:
    base = readiness_service.load_runner_config()
    return DeploymentConfig(
        pass_threshold=int(os.getenv("DEPLOY_PASS_THRESHOLD", str(base.pass_threshold))),
        critical_containers=base.critical_containers,
        fastapi_readyz_url=os.getenv("DEPLOY_FASTAPI_URL", base.fastapi_readyz_url),
        portal_url=os.getenv("DEPLOY_PORTAL_URL", "http://127.0.0.1:3000/api/health"),
        minio_health_url=os.getenv("DEPLOY_MINIO_HEALTH_URL", "http://127.0.0.1:9000/minio/health/ready"),
        prometheus_url=os.getenv("DEPLOY_PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/"),
        grafana_url=os.getenv("DEPLOY_GRAFANA_URL", "http://127.0.0.1:3001").rstrip("/"),
        kafka_exporter_url=base.kafka_exporter_url,
        redis_host=base.redis_host,
        redis_port=base.redis_port,
        redis_password=base.redis_password,
        backup_dir=os.getenv("DEPLOY_BACKUP_DIR", "/backups"),
        backup_globs=tuple(
            g.strip() for g in os.getenv("DEPLOY_BACKUP_GLOBS", "*.sql.gz,*.dump,*.sql,*.tar.zst").split(",")
            if g.strip()
        ),
        backup_max_age_hours=float(os.getenv("DEPLOY_BACKUP_MAX_AGE_HOURS", "24")),
        source=os.getenv("DEPLOY_SOURCE", "api"),
        tenant_id=os.getenv("DEPLOY_TENANT_ID", base.tenant_id),
    )


# --- Prometheus metrics (requirement 6) --------------------------------------
DEPLOYMENT_STATUS_G = Gauge(
    "diep_deployment_status",
    "Latest deployment gate posture (GO=1, IN_PROGRESS=0.5, NO_GO/FAILED/ROLLED_BACK=0)",
)
DEPLOYMENT_DURATION_G = Gauge(
    "diep_deployment_duration_seconds",
    "Duration of the latest completed production cutover, in seconds",
)
DEPLOYMENT_VALIDATION_SCORE_G = Gauge(
    "diep_deployment_validation_score",
    "Latest deployment post-cutover validation score (0-100)",
)
DEPLOYMENT_LAST_RUN_TS_G = Gauge(
    "diep_deployment_last_run_timestamp_seconds",
    "Unix timestamp of the latest production cutover run",
)


def _gate_metric_value(gate: GateStatus) -> float:
    return {"GO": 1.0, "IN_PROGRESS": 0.5}.get(gate, 0.0)


def refresh_prometheus_metrics() -> None:
    latest = fetch_latest_deployment()
    if latest is None:
        DEPLOYMENT_STATUS_G.set(0)
        DEPLOYMENT_DURATION_G.set(0)
        DEPLOYMENT_VALIDATION_SCORE_G.set(0)
        DEPLOYMENT_LAST_RUN_TS_G.set(0)
        return
    DEPLOYMENT_STATUS_G.set(_gate_metric_value(latest.deployment_status))
    DEPLOYMENT_DURATION_G.set(latest.duration_seconds or 0)
    DEPLOYMENT_VALIDATION_SCORE_G.set(latest.validation_score or 0)
    DEPLOYMENT_LAST_RUN_TS_G.set(latest.started_at.timestamp())


# --- probe helpers (all read-only) -------------------------------------------
def _result(name: str, status: CheckStatus, weight: int, critical: bool, message: str,
            observed: dict | None = None, threshold: dict | None = None) -> DeploymentCheckResult:
    score = weight if status == "PASS" else (weight // 2 if status == "WARN" else 0)
    return DeploymentCheckResult(
        check_name=name, status=status, weight=weight, score=score, critical=critical,
        message=message, observed=observed or {}, threshold=threshold or {},
    )


def _http_get(url: str, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (internal infra URLs)
        body = resp.read().decode("utf-8", "replace")
        return resp.status, body


def _score_validation(phase: str, checks: list[DeploymentCheckResult], pass_threshold: int,
                      checked_at: datetime) -> ValidationResult:
    total_weight = sum(c.weight for c in checks) or 1
    score = round(100 * sum(c.score for c in checks) / total_weight)
    critical_failures = [c.check_name for c in checks if c.status == "FAIL" and c.critical]
    status: ValidationStatus = "PASS" if (not critical_failures and score >= pass_threshold) else "FAIL"
    summary = {
        "checks_passed": sum(1 for c in checks if c.status == "PASS"),
        "checks_warned": sum(1 for c in checks if c.status == "WARN"),
        "checks_failed": sum(1 for c in checks if c.status == "FAIL"),
        "critical_failures": critical_failures,
        "host": socket.gethostname(),
    }
    return ValidationResult(
        phase=phase, status=status, score=score, pass_threshold=pass_threshold,
        checked_at=checked_at, checks=checks, summary=summary,
    )


# --- pre-cutover checks (requirement 1) --------------------------------------
def check_mw2_readiness(config: DeploymentConfig,
                        readiness_run: "readiness_service.ReadinessRunResponse | None") -> DeploymentCheckResult:
    if readiness_run is None:
        return _result("mw2_readiness_certification", "FAIL", 25, True,
                       "MW2 readiness assessment could not be computed")
    passed = readiness_run.status == "PASS" and readiness_run.score >= readiness_run.pass_threshold
    return _result(
        "mw2_readiness_certification", "PASS" if passed else "FAIL", 25, True,
        f"MW2 readiness {readiness_run.status} ({readiness_run.score}/{readiness_run.pass_threshold})",
        observed={"status": readiness_run.status, "score": readiness_run.score,
                  "run_id": readiness_run.run_id},
        threshold={"required_status": "PASS", "min_score": readiness_run.pass_threshold},
    )


def check_critical_containers(config: DeploymentConfig,
                              container_state: dict[str, dict[str, Any]]) -> DeploymentCheckResult:
    missing, unhealthy, running = [], [], []
    for name in config.critical_containers:
        state = container_state.get(name)
        if not state:
            missing.append(name)
            continue
        # readiness.inspect_containers returns a flattened snapshot:
        # {name, status, running, restart_count, started_at}
        if state.get("running") and state.get("status") == "running":
            running.append(name)
        else:
            unhealthy.append(name)
    if missing or unhealthy:
        return _result("critical_containers_healthy", "FAIL", 20, True,
                       f"{len(running)}/{len(config.critical_containers)} critical containers healthy",
                       observed={"running": running, "unhealthy": unhealthy, "missing": missing},
                       threshold={"all_running_and_healthy": True})
    return _result("critical_containers_healthy", "PASS", 20, True,
                   f"all {len(running)} critical containers running and healthy",
                   observed={"running": running})


def check_database_backups(config: DeploymentConfig) -> DeploymentCheckResult:
    threshold = {"backup_dir": config.backup_dir, "max_age_hours": config.backup_max_age_hours,
                 "globs": list(config.backup_globs)}
    root = Path(config.backup_dir)
    if not root.is_dir():
        return _result("database_backups_present", "FAIL", 20, True,
                       f"backup directory {config.backup_dir} not found",
                       observed={"exists": False}, threshold=threshold)
    matches: list[tuple[str, float]] = []
    for pattern in config.backup_globs:
        for p in root.glob(pattern):
            try:
                matches.append((p.name, p.stat().st_mtime))
            except OSError:
                continue
    if not matches:
        return _result("database_backups_present", "FAIL", 20, True,
                       "no backup artifacts found in backup directory",
                       observed={"count": 0}, threshold=threshold)
    newest_name, newest_mtime = max(matches, key=lambda m: m[1])
    age_hours = (time.time() - newest_mtime) / 3600.0
    observed = {"count": len(matches), "newest": newest_name, "newest_age_hours": round(age_hours, 2)}
    if age_hours > config.backup_max_age_hours:
        return _result("database_backups_present", "WARN", 20, True,
                       f"most recent backup is {age_hours:.1f}h old (older than {config.backup_max_age_hours}h)",
                       observed=observed, threshold=threshold)
    return _result("database_backups_present", "PASS", 20, True,
                   f"{len(matches)} backup artifact(s); newest {age_hours:.1f}h old",
                   observed=observed, threshold=threshold)


def check_minio_archive(config: DeploymentConfig) -> DeploymentCheckResult:
    try:
        status, _ = _http_get(config.minio_health_url, config.http_timeout_seconds)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result("minio_archive_accessible", "FAIL", 15, True,
                       f"MinIO health probe failed: {exc}",
                       observed={"url": config.minio_health_url}, threshold={"http_status": 200})
    ok = 200 <= status < 300
    return _result("minio_archive_accessible", "PASS" if ok else "FAIL", 15, True,
                   f"MinIO health {status}", observed={"http_status": status, "url": config.minio_health_url},
                   threshold={"http_status": "2xx"})


def _KAFKA_PROBE(cfg):
    return readiness_service.check_kafka_exporter_metrics(cfg)


def _REDIS_PROBE(cfg):
    return readiness_service.check_redis_connectivity(cfg)


def _named_readiness(name: str, weight: int, probe) -> DeploymentCheckResult:
    """Run a readiness probe and re-label the result under a deployment check name
    (the same Redis/Kafka probe serves both pre- and post-cutover under different
    check names)."""
    rc = _reuse_readiness_check(probe)
    if rc is None:
        return _result(name, "FAIL", weight, True, f"{name} probe unavailable")
    return _result(name, rc.status, weight, True, rc.message, observed=rc.observed, threshold=rc.threshold)


def check_kafka_health(config: DeploymentConfig) -> DeploymentCheckResult:
    return _named_readiness("kafka_health", 10, _KAFKA_PROBE)


def check_redis_health(config: DeploymentConfig) -> DeploymentCheckResult:
    return _named_readiness("redis_health", 10, _REDIS_PROBE)


def _reuse_readiness_check(fn) -> "readiness_service.ReadinessCheckResult | None":
    """Run a readiness probe against the shared readiness config; never raise."""
    try:
        cfg = readiness_service.load_runner_config()
        return fn(cfg)
    except Exception:
        return None


# --- post-cutover checks (requirement 3) -------------------------------------
def check_fastapi_readyz(config: DeploymentConfig) -> DeploymentCheckResult:
    try:
        status, _ = _http_get(config.fastapi_readyz_url, config.http_timeout_seconds)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result("fastapi_readyz", "FAIL", 25, True, f"FastAPI /readyz probe failed: {exc}",
                       observed={"url": config.fastapi_readyz_url}, threshold={"http_status": 200})
    ok = status == 200
    return _result("fastapi_readyz", "PASS" if ok else "FAIL", 25, True, f"FastAPI /readyz {status}",
                   observed={"http_status": status}, threshold={"http_status": 200})


def check_portal_login(config: DeploymentConfig) -> DeploymentCheckResult:
    """Read-only: probes the portal health/login surface is reachable (HTTP GET).
    It does NOT submit credentials — production-safe, non-mutating."""
    try:
        status, _ = _http_get(config.portal_url, config.http_timeout_seconds)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result("portal_login", "FAIL", 15, True, f"portal probe failed: {exc}",
                       observed={"url": config.portal_url}, threshold={"http_status": "2xx"})
    ok = 200 <= status < 400
    return _result("portal_login", "PASS" if ok else "FAIL", 15, True, f"portal reachable ({status})",
                   observed={"http_status": status, "url": config.portal_url},
                   threshold={"http_status": "2xx/3xx"})


def check_redis_connectivity(config: DeploymentConfig) -> DeploymentCheckResult:
    return _named_readiness("redis_connectivity", 10, _REDIS_PROBE)


def check_kafka_metrics(config: DeploymentConfig) -> DeploymentCheckResult:
    return _named_readiness("kafka_metrics", 10, _KAFKA_PROBE)


def check_prometheus_targets(config: DeploymentConfig) -> DeploymentCheckResult:
    url = f"{config.prometheus_url}/api/v1/targets"
    try:
        status, body = _http_get(url, config.http_timeout_seconds)
        import json
        data = json.loads(body)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result("prometheus_targets", "FAIL", 10, False, f"Prometheus targets probe failed: {exc}",
                       observed={"url": url}, threshold={"up_targets": ">0"})
    active = (data.get("data") or {}).get("activeTargets") or []
    up = [t for t in active if t.get("health") == "up"]
    down = [t.get("labels", {}).get("job") for t in active if t.get("health") == "down"]
    observed = {"http_status": status, "active": len(active), "up": len(up), "down": down}
    if not active:
        return _result("prometheus_targets", "WARN", 10, False, "no active Prometheus targets reported",
                       observed=observed, threshold={"up_targets": ">0"})
    if down:
        return _result("prometheus_targets", "WARN", 10, False, f"{len(down)} target(s) down",
                       observed=observed, threshold={"all_targets_up": True})
    return _result("prometheus_targets", "PASS", 10, False, f"all {len(up)} Prometheus targets up",
                   observed=observed, threshold={"all_targets_up": True})


def check_grafana_availability(config: DeploymentConfig) -> DeploymentCheckResult:
    url = f"{config.grafana_url}/api/health"
    try:
        status, _ = _http_get(url, config.http_timeout_seconds)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result("grafana_availability", "FAIL", 10, False, f"Grafana health probe failed: {exc}",
                       observed={"url": url}, threshold={"http_status": 200})
    ok = status == 200
    return _result("grafana_availability", "PASS" if ok else "FAIL", 10, False, f"Grafana health {status}",
                   observed={"http_status": status}, threshold={"http_status": 200})


# --- orchestration -----------------------------------------------------------
def run_pre_cutover_validation(config: DeploymentConfig,
                               readiness_run: "readiness_service.ReadinessRunResponse | None | str" = "auto",
                               ) -> tuple[ValidationResult, "readiness_service.ReadinessRunResponse | None"]:
    """Pre-cutover gate. Reuses the MW2 readiness assessment (computed fresh unless
    one is supplied) plus container / backup / archive / Kafka / Redis probes."""
    if readiness_run == "auto":
        try:
            previous = readiness_service.fetch_latest_readiness_run()
        except Exception:
            previous = None
        try:
            readiness_run = readiness_service.run_readiness_assessment(
                readiness_service.load_runner_config(), previous_run=previous)
        except Exception:
            readiness_run = None
    try:
        container_state = readiness_service.inspect_containers(config.critical_containers)
    except Exception:
        container_state = {}
    checks = [
        check_mw2_readiness(config, readiness_run),
        check_critical_containers(config, container_state),
        check_database_backups(config),
        check_minio_archive(config),
        check_kafka_health(config),
        check_redis_health(config),
    ]
    return _score_validation("pre_cutover", checks, config.pass_threshold,
                             datetime.now(timezone.utc)), readiness_run


def run_post_cutover_validation(config: DeploymentConfig) -> ValidationResult:
    """Post-cutover gate: verify the full live surface is healthy."""
    checks = [
        check_fastapi_readyz(config),
        check_portal_login(config),
        check_redis_connectivity(config),
        check_kafka_metrics(config),
        check_prometheus_targets(config),
        check_grafana_availability(config),
    ]
    return _score_validation("post_cutover", checks, config.pass_threshold,
                             datetime.now(timezone.utc))


def capture_baseline(config: DeploymentConfig,
                     readiness_run: "readiness_service.ReadinessRunResponse | None") -> dict[str, Any]:
    """Read-only snapshot of the system at cutover-start time."""
    try:
        container_state = readiness_service.inspect_containers(config.critical_containers)
    except Exception:
        container_state = {}
    containers = {}
    for name, state in container_state.items():
        started = state.get("started_at")
        containers[name] = {
            "status": state.get("status"),
            "running": bool(state.get("running")),
            "started_at": started.isoformat() if isinstance(started, datetime) else started,
            "restart_count": state.get("restart_count"),
        }
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "containers": containers,
        "readiness": ({"run_id": readiness_run.run_id, "status": readiness_run.status,
                       "score": readiness_run.score} if readiness_run else None),
        "critical_containers": list(config.critical_containers),
    }


def start_cutover(config: DeploymentConfig, operator: str, change_ref: str | None = None,
                  checklist: list[dict] | None = None, notes: str | None = None) -> DeploymentRecord:
    """Begin a production cutover: generate the deployment record + timestamp,
    capture a read-only baseline, run pre-cutover validation, and record the
    operator-attested checklist as audit events. Performs NO destructive action."""
    deployment_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    pre, readiness_run = run_pre_cutover_validation(config)
    baseline = capture_baseline(config, readiness_run)

    gate: GateStatus = "IN_PROGRESS"
    record = DeploymentRecord(
        deployment_id=deployment_id,
        started_at=started_at,
        status="STARTED",
        deployment_status=gate,
        operator=operator,
        change_ref=change_ref,
        validation_score=None,
        pass_threshold=config.pass_threshold,
        readiness_run_id=(readiness_run.run_id if readiness_run else None),
        baseline=baseline,
        pre_cutover=pre.model_dump(mode="json"),
        post_cutover={},
        evidence={"checklist": checklist or [], "notes": notes},
        source=config.source,
        tenant_id=config.tenant_id,
    )
    persist_deployment(record)
    record_event(deployment_id, "CUTOVER_STARTED", operator,
                 {"change_ref": change_ref, "pass_threshold": config.pass_threshold})
    record_event(deployment_id, "BASELINE_CAPTURED", operator,
                 {"containers": list(baseline.get("containers", {}).keys())})
    for item in (checklist or []):
        record_event(deployment_id, "CHECKLIST_ITEM", operator, item)
    if notes:
        record_event(deployment_id, "OPERATOR_NOTE", operator, {"notes": notes})
    record_event(deployment_id, "PRE_CUTOVER_VALIDATED", operator,
                 {"status": pre.status, "score": pre.score,
                  "critical_failures": pre.summary.get("critical_failures", [])})
    record.events = fetch_deployment_events(deployment_id)
    return record


def validate_cutover(config: DeploymentConfig, deployment_id: str, operator: str) -> DeploymentRecord:
    """Run post-cutover validation against an in-flight deployment, derive the GO/
    NO-GO gate, finalise duration/score, persist the result + evidence, and append
    the audit events. Read-only against infra."""
    record = fetch_deployment(deployment_id)
    if record is None:
        raise KeyError(deployment_id)
    post = run_post_cutover_validation(config)
    completed_at = datetime.now(timezone.utc)
    duration = (completed_at - record.started_at).total_seconds()
    gate: GateStatus = "GO" if post.status == "PASS" else "NO_GO"
    run_status: RunStatus = "VALIDATED" if post.status == "PASS" else "FAILED"

    evidence = dict(record.evidence or {})
    evidence["deployment_report"] = {
        "deployment_id": deployment_id, "operator": operator,
        "deployment_status": gate, "validation_score": post.score,
        "duration_seconds": duration,
    }
    evidence["readiness_report"] = record.baseline.get("readiness")
    evidence["health_snapshots"] = {
        "pre_cutover": record.pre_cutover.get("checks", []),
        "post_cutover": post.model_dump(mode="json").get("checks", []),
    }

    record.completed_at = completed_at
    record.duration_seconds = duration
    record.status = run_status
    record.deployment_status = gate
    record.validation_score = post.score
    record.post_cutover = post.model_dump(mode="json")
    record.evidence = evidence
    update_deployment(record)

    record_event(deployment_id, "POST_CUTOVER_VALIDATED", operator,
                 {"status": post.status, "score": post.score,
                  "critical_failures": post.summary.get("critical_failures", [])})
    record_event(deployment_id, "EVIDENCE_RECORDED", operator,
                 {"deployment_status": gate, "duration_seconds": round(duration, 3)})
    refresh_prometheus_metrics()
    record.events = fetch_deployment_events(deployment_id)
    return record


# --- persistence (additive tables only) --------------------------------------
def persist_deployment(record: DeploymentRecord) -> None:
    import psycopg2.extras as _ext
    common.execute(
        "INSERT INTO platform_deployment_runs "
        "(deployment_id, started_at, completed_at, status, deployment_status, operator, "
        " change_ref, validation_score, pass_threshold, duration_seconds, readiness_run_id, "
        " baseline, pre_cutover, post_cutover, evidence, source, tenant_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (record.deployment_id, record.started_at, record.completed_at, record.status,
         record.deployment_status, record.operator, record.change_ref, record.validation_score,
         record.pass_threshold, record.duration_seconds, record.readiness_run_id,
         _ext.Json(record.baseline), _ext.Json(record.pre_cutover), _ext.Json(record.post_cutover),
         _ext.Json(record.evidence), record.source, record.tenant_id),
    )


def update_deployment(record: DeploymentRecord) -> None:
    import psycopg2.extras as _ext
    common.execute(
        "UPDATE platform_deployment_runs SET completed_at=%s, status=%s, deployment_status=%s, "
        "validation_score=%s, duration_seconds=%s, post_cutover=%s, evidence=%s "
        "WHERE deployment_id=%s",
        (record.completed_at, record.status, record.deployment_status, record.validation_score,
         record.duration_seconds, _ext.Json(record.post_cutover), _ext.Json(record.evidence),
         record.deployment_id),
    )


def record_event(deployment_id: str, event_type: str, actor: str, detail: dict | None = None) -> None:
    import psycopg2.extras as _ext
    common.execute(
        "INSERT INTO platform_deployment_events (deployment_id, event_type, actor, detail) "
        "VALUES (%s,%s,%s,%s)",
        (deployment_id, event_type, actor, _ext.Json(detail or {})),
    )


def fetch_deployment_events(deployment_id: str) -> list[DeploymentEvent]:
    rows = common.query_all(
        "SELECT recorded_at, event_type, actor, detail FROM platform_deployment_events "
        "WHERE deployment_id=%s ORDER BY recorded_at, event_id", (deployment_id,))
    return [DeploymentEvent(recorded_at=r["recorded_at"], event_type=r["event_type"],
                            actor=r["actor"], detail=r["detail"] or {}) for r in rows]


def _row_to_record(row: dict[str, Any], events: list[DeploymentEvent] | None = None) -> DeploymentRecord:
    return DeploymentRecord(
        deployment_id=str(row["deployment_id"]),
        started_at=row["started_at"], completed_at=row.get("completed_at"),
        status=row["status"], deployment_status=row["deployment_status"], operator=row["operator"],
        change_ref=row.get("change_ref"), validation_score=row.get("validation_score"),
        pass_threshold=row["pass_threshold"], duration_seconds=row.get("duration_seconds"),
        readiness_run_id=(str(row["readiness_run_id"]) if row.get("readiness_run_id") else None),
        baseline=row.get("baseline") or {}, pre_cutover=row.get("pre_cutover") or {},
        post_cutover=row.get("post_cutover") or {}, evidence=row.get("evidence") or {},
        source=row.get("source", "api"), tenant_id=row.get("tenant_id", "default"),
        events=events or [],
    )


def _row_to_summary(row: dict[str, Any]) -> DeploymentSummary:
    return DeploymentSummary(
        deployment_id=str(row["deployment_id"]), started_at=row["started_at"],
        completed_at=row.get("completed_at"), status=row["status"],
        deployment_status=row["deployment_status"], operator=row["operator"],
        change_ref=row.get("change_ref"), validation_score=row.get("validation_score"),
        pass_threshold=row["pass_threshold"], duration_seconds=row.get("duration_seconds"),
    )


_RECORD_COLS = ("deployment_id, started_at, completed_at, status, deployment_status, operator, "
                "change_ref, validation_score, pass_threshold, duration_seconds, readiness_run_id, "
                "baseline, pre_cutover, post_cutover, evidence, source, tenant_id")


def fetch_deployment(deployment_id: str) -> DeploymentRecord | None:
    row = common.query_one(
        f"SELECT {_RECORD_COLS} FROM platform_deployment_runs WHERE deployment_id=%s",
        (deployment_id,))
    if not row:
        return None
    return _row_to_record(row, fetch_deployment_events(deployment_id))


def fetch_latest_deployment() -> DeploymentRecord | None:
    row = common.query_one(
        f"SELECT {_RECORD_COLS} FROM platform_deployment_runs ORDER BY started_at DESC LIMIT 1")
    if not row:
        return None
    return _row_to_record(row, fetch_deployment_events(str(row["deployment_id"])))


def fetch_deployment_history(limit: int = 50, since_hours: int = 720,
                             status: RunStatus | None = None) -> DeploymentHistoryResponse:
    limit = min(max(limit, 1), 500)
    since_hours = min(max(since_hours, 1), 24 * 365)
    clauses = ["started_at > now() - make_interval(hours => %s)"]
    params: list[Any] = [since_hours]
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses)
    total_row = common.query_one(
        f"SELECT COUNT(*) AS n FROM platform_deployment_runs {where}", tuple(params))
    rows = common.query_all(
        f"SELECT deployment_id, started_at, completed_at, status, deployment_status, operator, "
        f"change_ref, validation_score, pass_threshold, duration_seconds "
        f"FROM platform_deployment_runs {where} ORDER BY started_at DESC LIMIT %s",
        tuple(params + [limit]))
    return DeploymentHistoryResponse(
        total=int(total_row["n"]) if total_row else 0, limit=limit, since_hours=since_hours,
        status=status, runs=[_row_to_summary(r) for r in rows])
