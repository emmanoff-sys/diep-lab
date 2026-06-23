from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import psycopg2
import psycopg2.extras
import redis
from prometheus_client import Gauge
from pydantic import BaseModel, Field

import common

CheckStatus = Literal["PASS", "WARN", "FAIL"]
RunStatus = Literal["PASS", "FAIL"]

DEFAULT_CRITICAL_CONTAINERS = (
    "diep-fastapi",
    "diep-timescaledb",
    "diep-redis",
    "diep-redis-replica",
    "diep-kafka",
    "diep-kafka-exporter",
    "diep-minio",
)
READINESS_CHECK_NAMES = (
    "fastapi_readyz",
    "postgres_connectivity",
    "redis_connectivity",
    "kafka_broker_health",
    "kafka_exporter_metrics",
    "container_restart_counts",
    "disk_utilization",
    "memory_utilization",
    "critical_service_uptime",
)
_METRIC_LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)$"
)
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')
_DOCKER_TS_RE = re.compile(r"^(?P<head>.+\.\d{6})\d*(?P<tail>Z|[+-]\d\d:\d\d)$")


class ReadinessCheckResult(BaseModel):
    check_name: str
    status: CheckStatus
    weight: int
    score: int
    critical: bool = True
    message: str
    observed: dict[str, Any] = Field(default_factory=dict)
    threshold: dict[str, Any] = Field(default_factory=dict)


class ReadinessRunSummary(BaseModel):
    run_id: str
    checked_at: datetime
    status: RunStatus
    score: int = Field(ge=0, le=100)
    pass_threshold: int = Field(ge=0, le=100)
    recommendation: str
    source: str
    tenant_id: str
    summary: dict[str, Any] = Field(default_factory=dict)


class ReadinessRunResponse(ReadinessRunSummary):
    checks: list[ReadinessCheckResult] = Field(default_factory=list)


class ReadinessHistoryResponse(BaseModel):
    total: int
    limit: int
    since_hours: int
    status: RunStatus | None = None
    runs: list[ReadinessRunSummary] = Field(default_factory=list)


@dataclass
class ReadinessConfig:
    fastapi_readyz_url: str
    kafka_exporter_url: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    redis_host: str
    redis_port: int
    redis_password: str | None
    kafka_container: str
    docker_root_dir: str
    disk_max_used_pct: float
    memory_max_used_pct: float
    min_uptime_seconds: int
    max_restart_delta: int
    pass_threshold: int
    critical_containers: tuple[str, ...]
    source: str
    tenant_id: str
    connect_timeout_seconds: float = 3.0
    http_timeout_seconds: float = 5.0


READINESS_SCORE_G = Gauge(
    "diep_readiness_score",
    "Latest persisted MW2 readiness score (0-100)",
)
READINESS_PASS_G = Gauge(
    "diep_readiness_pass",
    "1 if the latest persisted MW2 readiness recommendation is PASS, else 0",
)
READINESS_LAST_RUN_TS_G = Gauge(
    "diep_readiness_last_run_timestamp_seconds",
    "Unix timestamp of the latest persisted MW2 readiness run",
)
READINESS_CHECK_STATUS_G = Gauge(
    "diep_readiness_check_status",
    "Latest persisted MW2 readiness status per check (PASS=1, WARN=0.5, FAIL=0)",
    ["check_name"],
)


def load_env_defaults(env_path: str | Path | None = None) -> None:
    """Best-effort `.env` loader for the host-side runner.

    The API container already gets its environment from docker-compose; the script
    may be launched directly on the host, where `set -a; . ./.env` is not always
    how operators prefer to work.
    """
    target = Path(env_path or Path(__file__).resolve().parent.parent / ".env")
    if not target.exists():
        return
    for raw_line in target.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_runner_config() -> ReadinessConfig:
    docker_root_dir = os.getenv("READINESS_DOCKER_ROOT_DIR") or _docker_root_dir() or "/var/lib/docker"
    return ReadinessConfig(
        fastapi_readyz_url=os.getenv("READINESS_FASTAPI_URL", "http://127.0.0.1:8000/readyz"),
        kafka_exporter_url=os.getenv("READINESS_KAFKA_EXPORTER_URL", "http://127.0.0.1:9308/metrics"),
        db_host=os.getenv("READINESS_DB_HOST") or os.getenv("DB_HOST", "127.0.0.1"),
        db_port=int(os.getenv("READINESS_DB_PORT", os.getenv("DB_PORT", "5432"))),
        db_name=os.getenv("READINESS_DB_NAME", os.getenv("DB_NAME", "diep")),
        db_user=os.getenv("READINESS_DB_USER", os.getenv("DB_USER", "diep")),
        db_password=os.getenv("READINESS_DB_PASSWORD", os.getenv("DB_PASSWORD", "")),
        redis_host=os.getenv("READINESS_REDIS_HOST", "127.0.0.1"),
        redis_port=int(os.getenv("READINESS_REDIS_PORT", "6379")),
        redis_password=os.getenv("READINESS_REDIS_PASSWORD") or os.getenv("REDIS_PASSWORD") or None,
        kafka_container=os.getenv("READINESS_KAFKA_CONTAINER", "diep-kafka"),
        docker_root_dir=docker_root_dir,
        disk_max_used_pct=float(os.getenv("READINESS_DISK_MAX_USED_PCT", "85")),
        memory_max_used_pct=float(os.getenv("READINESS_MEMORY_MAX_USED_PCT", "85")),
        min_uptime_seconds=int(os.getenv("READINESS_MIN_UPTIME_SECONDS", "86400")),
        max_restart_delta=int(os.getenv("READINESS_MAX_RESTART_DELTA", "0")),
        pass_threshold=int(os.getenv("READINESS_PASS_THRESHOLD", "90")),
        critical_containers=tuple(
            c.strip()
            for c in os.getenv("READINESS_CRITICAL_CONTAINERS", ",".join(DEFAULT_CRITICAL_CONTAINERS)).split(",")
            if c.strip()
        ),
        source=os.getenv("READINESS_SOURCE", "scripts/run_mw2_readiness_check.py"),
        tenant_id=os.getenv("READINESS_TENANT_ID", "default"),
    )


def run_readiness_assessment(config: ReadinessConfig, previous_run: ReadinessRunResponse | None = None) -> ReadinessRunResponse:
    checked_at = datetime.now(timezone.utc)
    container_state = inspect_containers(config.critical_containers)

    checks = [
        check_fastapi_readyz(config),
        check_postgres_connectivity(config),
        check_redis_connectivity(config),
        check_kafka_broker_health(config),
        check_kafka_exporter_metrics(config),
        check_container_restart_counts(config, container_state, previous_run),
        check_disk_utilization(config),
        check_memory_utilization(config),
        check_critical_service_uptime(config, container_state),
    ]

    failed = [check for check in checks if check.status == "FAIL"]
    warned = [check for check in checks if check.status == "WARN"]
    passed = [check for check in checks if check.status == "PASS"]
    score = sum(check.score for check in checks)
    min_uptime = _minimum_uptime_seconds(container_state)
    max_restart_delta = _maximum_restart_delta(checks)

    recommendation_parts = []
    if failed:
        recommendation_parts.append(
            "FAIL — keep MW2 blocked until the failing checks are clean"
        )
        if any(check.check_name == "critical_service_uptime" for check in failed):
            recommendation_parts.append(
                f"the 24-hour stability window is incomplete (minimum uptime {int(min_uptime)}s, target {config.min_uptime_seconds}s)"
            )
        if any(check.check_name == "container_restart_counts" for check in failed):
            recommendation_parts.append(
                f"container restart delta exceeded the allowed threshold ({max_restart_delta}>{config.max_restart_delta})"
            )
    else:
        recommendation_parts.append(
            "PASS — MW2 may proceed if the scheduled change window and sign-offs are otherwise ready"
        )
        if warned:
            recommendation_parts.append(
                "review the warning-level checks before scheduling"
            )
    recommendation = "; ".join(recommendation_parts)
    run_status: RunStatus = "PASS" if (not failed and score >= config.pass_threshold) else "FAIL"

    summary = {
        "checks_passed": len(passed),
        "checks_warned": len(warned),
        "checks_failed": len(failed),
        "critical_failures": [check.check_name for check in failed if check.critical],
        "critical_containers": list(config.critical_containers),
        "minimum_uptime_seconds": min_uptime,
        "required_uptime_seconds": config.min_uptime_seconds,
        "maximum_restart_delta": max_restart_delta,
        "allowed_restart_delta": config.max_restart_delta,
        "docker_root_dir": config.docker_root_dir,
        "host": socket.gethostname(),
    }

    return ReadinessRunResponse(
        run_id=str(uuid.uuid4()),
        checked_at=checked_at,
        status=run_status,
        score=score,
        pass_threshold=config.pass_threshold,
        recommendation=recommendation,
        source=config.source,
        tenant_id=config.tenant_id,
        summary=summary,
        checks=checks,
    )


def fetch_latest_readiness_run() -> ReadinessRunResponse | None:
    row = common.query_one(
        "SELECT run_id, checked_at, status, score, pass_threshold, recommendation, "
        "source, tenant_id, summary, checks "
        "FROM platform_readiness_reports ORDER BY checked_at DESC LIMIT 1"
    )
    return _row_to_run(row) if row else None


def fetch_readiness_history(limit: int = 50, since_hours: int = 168, status: RunStatus | None = None) -> ReadinessHistoryResponse:
    limit = min(max(limit, 1), 500)
    since_hours = min(max(since_hours, 1), 24 * 365)
    clauses = ["checked_at > now() - make_interval(hours => %s)"]
    params: list[Any] = [since_hours]
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses)
    total_row = common.query_one(
        f"SELECT COUNT(*) AS n FROM platform_readiness_reports {where}",
        tuple(params),
    )
    rows = common.query_all(
        f"SELECT run_id, checked_at, status, score, pass_threshold, recommendation, "
        f"source, tenant_id, summary "
        f"FROM platform_readiness_reports {where} ORDER BY checked_at DESC LIMIT %s",
        tuple(params + [limit]),
    )
    return ReadinessHistoryResponse(
        total=int(total_row["n"]) if total_row else 0,
        limit=limit,
        since_hours=since_hours,
        status=status,
        runs=[_row_to_summary(row) for row in rows],
    )


def persist_readiness_run(run: ReadinessRunResponse, config: ReadinessConfig) -> None:
    conn = psycopg2.connect(
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
        connect_timeout=int(config.connect_timeout_seconds),
    )
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO platform_readiness_reports "
            "(run_id, checked_at, status, score, pass_threshold, recommendation, source, tenant_id, summary, checks) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                run.run_id,
                run.checked_at,
                run.status,
                run.score,
                run.pass_threshold,
                run.recommendation,
                run.source,
                run.tenant_id,
                psycopg2.extras.Json(run.summary),
                psycopg2.extras.Json([check.model_dump(mode="json") for check in run.checks]),
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def refresh_prometheus_metrics() -> None:
    latest = fetch_latest_readiness_run()
    if latest is None:
        READINESS_SCORE_G.set(0)
        READINESS_PASS_G.set(0)
        READINESS_LAST_RUN_TS_G.set(0)
        for check_name in READINESS_CHECK_NAMES:
            READINESS_CHECK_STATUS_G.labels(check_name).set(0)
        return

    READINESS_SCORE_G.set(latest.score)
    READINESS_PASS_G.set(1 if latest.status == "PASS" else 0)
    READINESS_LAST_RUN_TS_G.set(latest.checked_at.timestamp())
    check_map = {check.check_name: check for check in latest.checks}
    for check_name in READINESS_CHECK_NAMES:
        check = check_map.get(check_name)
        if check is None:
            READINESS_CHECK_STATUS_G.labels(check_name).set(0)
            continue
        READINESS_CHECK_STATUS_G.labels(check_name).set(
            1 if check.status == "PASS" else 0.5 if check.status == "WARN" else 0
        )


def inspect_containers(container_names: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if not container_names:
        return {}
    proc = _run_command(["docker", "inspect", *container_names], timeout=10)
    payload = json.loads(proc.stdout)
    snapshots: dict[str, dict[str, Any]] = {}
    for item in payload:
        name = item.get("Name", "").lstrip("/")
        state = item.get("State") or {}
        started_at = state.get("StartedAt")
        snapshots[name] = {
            "name": name,
            "status": state.get("Status", "unknown"),
            "running": bool(state.get("Running")),
            "restart_count": int(item.get("RestartCount", 0)),
            "started_at": parse_docker_timestamp(started_at) if started_at else None,
        }
    return snapshots


def check_fastapi_readyz(config: ReadinessConfig) -> ReadinessCheckResult:
    try:
        status_code, payload = _http_json(config.fastapi_readyz_url, timeout=config.http_timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        return _fail_result(
            "fastapi_readyz",
            weight=15,
            message=f"/readyz check failed: {exc}",
            observed={"url": config.fastapi_readyz_url},
        )

    ready = bool(payload.get("ready"))
    checks = payload.get("checks") or {}
    if status_code == 200 and ready:
        return _pass_result(
            "fastapi_readyz",
            weight=15,
            message="/readyz returned ready=true",
            observed={"url": config.fastapi_readyz_url, "status_code": status_code, "checks": checks},
        )
    return _fail_result(
        "fastapi_readyz",
        weight=15,
        message="/readyz did not report ready=true",
        observed={"url": config.fastapi_readyz_url, "status_code": status_code, "checks": checks},
    )


def check_postgres_connectivity(config: ReadinessConfig) -> ReadinessCheckResult:
    try:
        conn = psycopg2.connect(
            host=config.db_host,
            port=config.db_port,
            database=config.db_name,
            user=config.db_user,
            password=config.db_password,
            connect_timeout=int(config.connect_timeout_seconds),
        )
        cur = conn.cursor()
        cur.execute("SELECT current_database(), current_user")
        database_name, current_user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return _fail_result(
            "postgres_connectivity",
            weight=10,
            message=f"PostgreSQL connectivity check failed: {exc}",
            observed={"host": config.db_host, "port": config.db_port, "database": config.db_name},
        )

    return _pass_result(
        "postgres_connectivity",
        weight=10,
        message="PostgreSQL connectivity verified",
        observed={
            "host": config.db_host,
            "port": config.db_port,
            "database": database_name,
            "user": current_user,
        },
    )


def check_redis_connectivity(config: ReadinessConfig) -> ReadinessCheckResult:
    client = redis.Redis(
        host=config.redis_host,
        port=config.redis_port,
        password=config.redis_password,
        socket_connect_timeout=config.connect_timeout_seconds,
        socket_timeout=config.connect_timeout_seconds,
        decode_responses=True,
    )
    try:
        pong = client.ping()
        info = client.info(section="server")
    except Exception as exc:  # noqa: BLE001
        return _fail_result(
            "redis_connectivity",
            weight=10,
            message=f"Redis connectivity/authentication failed: {exc}",
            observed={"host": config.redis_host, "port": config.redis_port},
        )

    if pong:
        return _pass_result(
            "redis_connectivity",
            weight=10,
            message="Redis connectivity and authentication verified",
            observed={
                "host": config.redis_host,
                "port": config.redis_port,
                "redis_version": info.get("redis_version"),
            },
        )
    return _fail_result(
        "redis_connectivity",
        weight=10,
        message="Redis ping returned false",
        observed={"host": config.redis_host, "port": config.redis_port},
    )


def check_kafka_broker_health(config: ReadinessConfig) -> ReadinessCheckResult:
    try:
        proc = _run_command(
            [
                "docker",
                "exec",
                config.kafka_container,
                "/opt/kafka/bin/kafka-topics.sh",
                "--bootstrap-server",
                "localhost:9092",
                "--list",
            ],
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail_result(
            "kafka_broker_health",
            weight=15,
            message=f"Kafka broker health check failed: {exc}",
            observed={"container": config.kafka_container},
        )

    topics = sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())
    expected = {"__consumer_offsets", "diep.commands"}
    if expected.issubset(set(topics)):
        return _pass_result(
            "kafka_broker_health",
            weight=15,
            message="Kafka broker answered topic listing with expected topics present",
            observed={"container": config.kafka_container, "topics": topics},
        )
    return _fail_result(
        "kafka_broker_health",
        weight=15,
        message="Kafka broker topic listing succeeded but expected topics were missing",
        observed={"container": config.kafka_container, "topics": topics},
        threshold={"expected_topics": sorted(expected)},
    )


def check_kafka_exporter_metrics(config: ReadinessConfig) -> ReadinessCheckResult:
    try:
        status_code, text = _http_text(config.kafka_exporter_url, timeout=config.http_timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        return _fail_result(
            "kafka_exporter_metrics",
            weight=10,
            message=f"Kafka exporter metrics check failed: {exc}",
            observed={"url": config.kafka_exporter_url},
        )

    broker_count = find_metric_value(text, "kafka_brokers")
    broker_info = find_metric_value(text, "kafka_broker_info", {"address": "diep-kafka:9092", "id": "1"})
    topic_partitions = find_metric_value(text, "kafka_topic_partitions", {"topic": "diep.commands"})
    lag_sum = find_metric_value(text, "kafka_consumergroup_lag_sum", {"consumergroup": "diep-command-dispatcher", "topic": "diep.commands"})

    if status_code == 200 and broker_count is not None and broker_info is not None and topic_partitions is not None:
        return _pass_result(
            "kafka_exporter_metrics",
            weight=10,
            message="Kafka exporter metrics are available",
            observed={
                "url": config.kafka_exporter_url,
                "kafka_brokers": broker_count,
                "kafka_broker_info": broker_info,
                "diep_commands_partitions": topic_partitions,
                "dispatcher_lag_sum": lag_sum,
            },
        )
    return _fail_result(
        "kafka_exporter_metrics",
        weight=10,
        message="Kafka exporter metrics endpoint was reachable but required metrics were missing",
        observed={
            "url": config.kafka_exporter_url,
            "status_code": status_code,
            "kafka_brokers": broker_count,
            "kafka_broker_info": broker_info,
            "diep_commands_partitions": topic_partitions,
        },
    )


def check_container_restart_counts(
    config: ReadinessConfig,
    container_state: dict[str, dict[str, Any]],
    previous_run: ReadinessRunResponse | None,
) -> ReadinessCheckResult:
    current_counts = {
        name: container_state.get(name, {}).get("restart_count")
        for name in config.critical_containers
    }
    previous_counts = _previous_restart_counts(previous_run)
    deltas: dict[str, int | None] = {}
    for name, current_value in current_counts.items():
        previous_value = previous_counts.get(name)
        if previous_value is None or current_value is None:
            deltas[name] = None
        else:
            deltas[name] = int(current_value) - int(previous_value)

    known_deltas = [delta for delta in deltas.values() if delta is not None]
    max_delta = max(known_deltas) if known_deltas else 0

    if previous_run is None:
        return _pass_result(
            "container_restart_counts",
            weight=10,
            message="Container restart baseline established; future runs will fail on restart deltas above threshold",
            observed={"restart_counts": current_counts, "restart_deltas": deltas},
            threshold={"max_restart_delta": config.max_restart_delta},
        )

    offenders = {name: delta for name, delta in deltas.items() if delta is not None and delta > config.max_restart_delta}
    if offenders:
        return _fail_result(
            "container_restart_counts",
            weight=10,
            message="One or more critical containers restarted during the observation window",
            observed={"restart_counts": current_counts, "restart_deltas": deltas, "offenders": offenders},
            threshold={"max_restart_delta": config.max_restart_delta},
        )

    return _pass_result(
        "container_restart_counts",
        weight=10,
        message="No critical container restart deltas exceeded the allowed threshold",
        observed={"restart_counts": current_counts, "restart_deltas": deltas, "maximum_delta": max_delta},
        threshold={"max_restart_delta": config.max_restart_delta},
    )


def check_disk_utilization(config: ReadinessConfig) -> ReadinessCheckResult:
    total, used, free = shutil.disk_usage(config.docker_root_dir)
    used_pct = (used / total) * 100 if total else 0.0
    status: CheckStatus = "PASS" if used_pct <= config.disk_max_used_pct else "FAIL"
    factory = _pass_result if status == "PASS" else _fail_result
    return factory(
        "disk_utilization",
        weight=10,
        message=(
            f"Disk utilization {used_pct:.1f}% is within threshold"
            if status == "PASS"
            else f"Disk utilization {used_pct:.1f}% exceeds threshold"
        ),
        observed={
            "path": config.docker_root_dir,
            "used_percent": round(used_pct, 2),
            "free_bytes": free,
            "total_bytes": total,
        },
        threshold={"max_used_percent": config.disk_max_used_pct},
    )


def check_memory_utilization(config: ReadinessConfig) -> ReadinessCheckResult:
    meminfo = _read_meminfo()
    total_kb = meminfo.get("MemTotal", 0)
    available_kb = meminfo.get("MemAvailable", 0)
    used_pct = (1 - (available_kb / total_kb)) * 100 if total_kb else 0.0
    status: CheckStatus = "PASS" if used_pct <= config.memory_max_used_pct else "FAIL"
    factory = _pass_result if status == "PASS" else _fail_result
    return factory(
        "memory_utilization",
        weight=10,
        message=(
            f"Memory utilization {used_pct:.1f}% is within threshold"
            if status == "PASS"
            else f"Memory utilization {used_pct:.1f}% exceeds threshold"
        ),
        observed={
            "used_percent": round(used_pct, 2),
            "total_kb": total_kb,
            "available_kb": available_kb,
        },
        threshold={"max_used_percent": config.memory_max_used_pct},
    )


def check_critical_service_uptime(
    config: ReadinessConfig,
    container_state: dict[str, dict[str, Any]],
) -> ReadinessCheckResult:
    now = datetime.now(timezone.utc)
    uptimes: dict[str, int | None] = {}
    offenders: dict[str, Any] = {}
    for name in config.critical_containers:
        snapshot = container_state.get(name) or {}
        started_at = snapshot.get("started_at")
        if not snapshot.get("running"):
            uptimes[name] = None
            offenders[name] = {"status": snapshot.get("status", "missing"), "reason": "not running"}
            continue
        if started_at is None:
            uptimes[name] = None
            offenders[name] = {"status": snapshot.get("status", "unknown"), "reason": "missing started_at"}
            continue
        uptime = int((now - started_at).total_seconds())
        uptimes[name] = uptime
        if uptime < config.min_uptime_seconds:
            offenders[name] = {"uptime_seconds": uptime}

    if offenders:
        return _fail_result(
            "critical_service_uptime",
            weight=10,
            message="One or more critical services have not met the minimum uptime requirement",
            observed={"uptime_seconds": uptimes, "offenders": offenders},
            threshold={"minimum_seconds": config.min_uptime_seconds},
        )

    return _pass_result(
        "critical_service_uptime",
        weight=10,
        message="All critical services satisfy the minimum uptime requirement",
        observed={"uptime_seconds": uptimes},
        threshold={"minimum_seconds": config.min_uptime_seconds},
    )


def parse_docker_timestamp(value: str) -> datetime:
    match = _DOCKER_TS_RE.match(value)
    if match:
        value = f"{match.group('head')}{match.group('tail')}"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def find_metric_value(text: str, metric_name: str, labels: dict[str, str] | None = None) -> float | None:
    target = labels or {}
    for name, sample_labels, value in iter_metric_samples(text):
        if name != metric_name:
            continue
        if all(sample_labels.get(key) == expected for key, expected in target.items()):
            return value
    return None


def iter_metric_samples(text: str):
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE_RE.match(line)
        if not match:
            continue
        labels: dict[str, str] = {}
        label_blob = match.group(2) or ""
        for label_match in _LABEL_RE.finditer(label_blob):
            labels[label_match.group(1)] = bytes(label_match.group(2), "utf-8").decode("unicode_escape")
        yield match.group(1), labels, float(match.group(3))


def _read_meminfo() -> dict[str, int]:
    parsed: dict[str, int] = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            if ":" not in line:
                continue
            key, raw_value = line.split(":", 1)
            parts = raw_value.strip().split()
            if not parts:
                continue
            try:
                parsed[key] = int(parts[0])
            except ValueError:
                continue
    return parsed


def _run_command(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def _http_json(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8") or "{}")
        return response.status, payload


def _http_text(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def _docker_root_dir() -> str | None:
    try:
        proc = _run_command(["docker", "info", "--format", "{{ .DockerRootDir }}"], timeout=5)
    except Exception:  # noqa: BLE001
        return None
    value = proc.stdout.strip()
    return value or None


def _previous_restart_counts(previous_run: ReadinessRunResponse | None) -> dict[str, int]:
    if previous_run is None:
        return {}
    for check in previous_run.checks:
        if check.check_name == "container_restart_counts":
            observed = check.observed or {}
            raw = observed.get("restart_counts") or {}
            return {
                name: int(value)
                for name, value in raw.items()
                if value is not None
            }
    return {}


def _minimum_uptime_seconds(container_state: dict[str, dict[str, Any]]) -> int:
    now = datetime.now(timezone.utc)
    uptimes = []
    for snapshot in container_state.values():
        started_at = snapshot.get("started_at")
        if snapshot.get("running") and started_at is not None:
            uptimes.append(int((now - started_at).total_seconds()))
    return min(uptimes) if uptimes else 0


def _maximum_restart_delta(checks: list[ReadinessCheckResult]) -> int:
    for check in checks:
        if check.check_name != "container_restart_counts":
            continue
        deltas = [
            int(value)
            for value in (check.observed or {}).get("restart_deltas", {}).values()
            if value is not None
        ]
        return max(deltas) if deltas else 0
    return 0


def _pass_result(
    check_name: str,
    weight: int,
    message: str,
    observed: dict[str, Any],
    threshold: dict[str, Any] | None = None,
    critical: bool = True,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        check_name=check_name,
        status="PASS",
        weight=weight,
        score=weight,
        critical=critical,
        message=message,
        observed=observed,
        threshold=threshold or {},
    )


def _warn_result(
    check_name: str,
    weight: int,
    message: str,
    observed: dict[str, Any],
    threshold: dict[str, Any] | None = None,
    critical: bool = True,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        check_name=check_name,
        status="WARN",
        weight=weight,
        score=weight // 2,
        critical=critical,
        message=message,
        observed=observed,
        threshold=threshold or {},
    )


def _fail_result(
    check_name: str,
    weight: int,
    message: str,
    observed: dict[str, Any],
    threshold: dict[str, Any] | None = None,
    critical: bool = True,
) -> ReadinessCheckResult:
    return ReadinessCheckResult(
        check_name=check_name,
        status="FAIL",
        weight=weight,
        score=0,
        critical=critical,
        message=message,
        observed=observed,
        threshold=threshold or {},
    )


def _row_to_summary(row: dict[str, Any]) -> ReadinessRunSummary:
    normalized = dict(row)
    normalized["run_id"] = str(normalized["run_id"])
    return ReadinessRunSummary(**normalized)


def _row_to_run(row: dict[str, Any]) -> ReadinessRunResponse:
    normalized = dict(row)
    normalized["run_id"] = str(normalized["run_id"])
    return ReadinessRunResponse(**normalized)

