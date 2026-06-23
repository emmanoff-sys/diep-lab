"""Phase 24 — Production Cutover Automation unit tests (pure; no DB/network).

Run:  python -m pytest tests/test_deployment_unit.py -q
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

import deployment as dep  # noqa: E402
import readiness as readiness_service  # noqa: E402


def _cfg(**overrides):
    base = dict(
        pass_threshold=90,
        critical_containers=("diep-fastapi", "diep-timescaledb"),
        fastapi_readyz_url="http://x/readyz",
        portal_url="http://x/health",
        minio_health_url="http://x/minio",
        prometheus_url="http://x",
        grafana_url="http://x",
        kafka_exporter_url="http://x/metrics",
        redis_host="x", redis_port=6379, redis_password=None,
        backup_dir="/nonexistent", backup_globs=("*.sql",), backup_max_age_hours=24,
        source="pytest", tenant_id="default",
    )
    base.update(overrides)
    return dep.DeploymentConfig(**base)


def _readiness_run(status="PASS", score=95):
    return readiness_service.ReadinessRunResponse(
        run_id="r-1", checked_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        status=status, score=score, pass_threshold=90, recommendation="ok",
        source="pytest", tenant_id="default", summary={}, checks=[])


# --- scoring -----------------------------------------------------------------
def test_result_scoring_weights():
    assert dep._result("c", "PASS", 20, True, "").score == 20
    assert dep._result("c", "WARN", 20, True, "").score == 10
    assert dep._result("c", "FAIL", 20, True, "").score == 0


def test_score_validation_pass_and_fail():
    passing = [dep._result("a", "PASS", 50, True, ""), dep._result("b", "PASS", 50, True, "")]
    res = dep._score_validation("post_cutover", passing, 90, datetime.now(timezone.utc))
    assert res.status == "PASS" and res.score == 100

    # a critical FAIL forces FAIL even if the numeric score clears the threshold
    mixed = [dep._result("a", "PASS", 95, False, ""), dep._result("b", "FAIL", 5, True, "")]
    res2 = dep._score_validation("post_cutover", mixed, 90, datetime.now(timezone.utc))
    assert res2.status == "FAIL"
    assert res2.summary["critical_failures"] == ["b"]

    # below threshold (no critical fail, but a non-critical warn drags the score)
    low = [dep._result("a", "PASS", 50, True, ""), dep._result("b", "FAIL", 50, False, "")]
    res3 = dep._score_validation("post_cutover", low, 90, datetime.now(timezone.utc))
    assert res3.score == 50 and res3.status == "FAIL"


def test_gate_metric_value():
    assert dep._gate_metric_value("GO") == 1.0
    assert dep._gate_metric_value("IN_PROGRESS") == 0.5
    assert dep._gate_metric_value("NO_GO") == 0.0


# --- pre-cutover checks ------------------------------------------------------
def test_mw2_readiness_check():
    assert dep.check_mw2_readiness(_cfg(), _readiness_run("PASS", 95)).status == "PASS"
    assert dep.check_mw2_readiness(_cfg(), _readiness_run("FAIL", 80)).status == "FAIL"
    assert dep.check_mw2_readiness(_cfg(), None).status == "FAIL"


def test_critical_containers_check():
    healthy = {"diep-fastapi": {"running": True, "status": "running"},
               "diep-timescaledb": {"running": True, "status": "running"}}
    assert dep.check_critical_containers(_cfg(), healthy).status == "PASS"

    one_down = {"diep-fastapi": {"running": True, "status": "running"},
                "diep-timescaledb": {"running": False, "status": "exited"}}
    r = dep.check_critical_containers(_cfg(), one_down)
    assert r.status == "FAIL" and r.observed["unhealthy"] == ["diep-timescaledb"]

    missing = {"diep-fastapi": {"running": True, "status": "running"}}
    assert dep.check_critical_containers(_cfg(), missing).observed["missing"] == ["diep-timescaledb"]


def test_database_backups_check(tmp_path):
    # missing dir -> FAIL
    assert dep.check_database_backups(_cfg(backup_dir=str(tmp_path / "nope"))).status == "FAIL"
    # empty dir -> FAIL
    assert dep.check_database_backups(_cfg(backup_dir=str(tmp_path))).status == "FAIL"
    # fresh backup -> PASS
    fresh = tmp_path / "diep.sql"
    fresh.write_text("-- dump")
    assert dep.check_database_backups(_cfg(backup_dir=str(tmp_path))).status == "PASS"
    # stale backup -> WARN
    old = time.time() - 48 * 3600
    os.utime(fresh, (old, old))
    assert dep.check_database_backups(_cfg(backup_dir=str(tmp_path), backup_max_age_hours=24)).status == "WARN"


# --- post-cutover checks -----------------------------------------------------
def test_prometheus_targets_check(monkeypatch):
    def all_up(url, timeout):
        return 200, json.dumps({"data": {"activeTargets": [
            {"health": "up", "labels": {"job": "fastapi"}},
            {"health": "up", "labels": {"job": "kafka"}}]}})
    monkeypatch.setattr(dep, "_http_get", all_up)
    assert dep.check_prometheus_targets(_cfg()).status == "PASS"

    def one_down(url, timeout):
        return 200, json.dumps({"data": {"activeTargets": [
            {"health": "up", "labels": {"job": "fastapi"}},
            {"health": "down", "labels": {"job": "kafka"}}]}})
    monkeypatch.setattr(dep, "_http_get", one_down)
    r = dep.check_prometheus_targets(_cfg())
    assert r.status == "WARN" and r.observed["down"] == ["kafka"]


def test_post_cutover_validation_all_pass(monkeypatch):
    monkeypatch.setattr(dep, "_http_get", lambda url, timeout: (200, json.dumps(
        {"data": {"activeTargets": [{"health": "up", "labels": {"job": "x"}}]}})))
    monkeypatch.setattr(dep, "_reuse_readiness_check", lambda fn: readiness_service.ReadinessCheckResult(
        check_name="x", status="PASS", weight=10, score=10, message="ok"))
    res = dep.run_post_cutover_validation(_cfg())
    assert res.phase == "post_cutover"
    assert res.status == "PASS" and res.score == 100
    assert {c.check_name for c in res.checks} == set(dep.POST_CUTOVER_CHECK_NAMES)


def test_post_cutover_validation_fastapi_down(monkeypatch):
    def boom(url, timeout):
        raise OSError("connection refused")
    monkeypatch.setattr(dep, "_http_get", boom)
    monkeypatch.setattr(dep, "_reuse_readiness_check", lambda fn: None)
    res = dep.run_post_cutover_validation(_cfg())
    assert res.status == "FAIL"
    assert "fastapi_readyz" in res.summary["critical_failures"]


def test_http_probe_failure_branches(monkeypatch):
    def boom(url, timeout):
        raise OSError("refused")
    monkeypatch.setattr(dep, "_http_get", boom)
    assert dep.check_minio_archive(_cfg()).status == "FAIL"
    assert dep.check_fastapi_readyz(_cfg()).status == "FAIL"
    assert dep.check_portal_login(_cfg()).status == "FAIL"
    assert dep.check_grafana_availability(_cfg()).status == "FAIL"
    assert dep.check_prometheus_targets(_cfg()).status == "FAIL"


def test_http_probe_non_2xx(monkeypatch):
    monkeypatch.setattr(dep, "_http_get", lambda url, timeout: (503, ""))
    assert dep.check_minio_archive(_cfg()).status == "FAIL"
    assert dep.check_fastapi_readyz(_cfg()).status == "FAIL"
    assert dep.check_grafana_availability(_cfg()).status == "FAIL"
    # portal accepts 2xx/3xx; 503 is a fail
    assert dep.check_portal_login(_cfg()).status == "FAIL"


def test_prometheus_no_active_targets(monkeypatch):
    monkeypatch.setattr(dep, "_http_get", lambda url, timeout: (200, json.dumps({"data": {"activeTargets": []}})))
    assert dep.check_prometheus_targets(_cfg()).status == "WARN"


def test_reuse_readiness_check_swallows_errors(monkeypatch):
    def boom(cfg=None):
        raise RuntimeError("boom")
    monkeypatch.setattr(readiness_service, "load_runner_config", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert dep._reuse_readiness_check(lambda cfg: None) is None
    assert dep.check_redis_health(_cfg()).status == "FAIL"
    assert dep.check_kafka_metrics(_cfg()).status == "FAIL"


def test_refresh_prometheus_metrics_no_latest(monkeypatch):
    monkeypatch.setattr(dep, "fetch_latest_deployment", lambda: None)
    dep.refresh_prometheus_metrics()  # must not raise with no history


def test_refresh_prometheus_metrics_with_latest(monkeypatch):
    rec = dep.DeploymentRecord(
        deployment_id="d1", started_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        status="VALIDATED", deployment_status="GO", operator="x",
        pass_threshold=90, validation_score=100, duration_seconds=42.0)
    monkeypatch.setattr(dep, "fetch_latest_deployment", lambda: rec)
    dep.refresh_prometheus_metrics()
    assert dep.DEPLOYMENT_STATUS_G._value.get() == 1.0
    assert dep.DEPLOYMENT_VALIDATION_SCORE_G._value.get() == 100


def test_capture_baseline_tolerates_inspect_failure(monkeypatch):
    monkeypatch.setattr(readiness_service, "inspect_containers",
                        lambda names: (_ for _ in ()).throw(OSError("docker down")))
    base = dep.capture_baseline(_cfg(), None)
    assert base["containers"] == {} and base["readiness"] is None
