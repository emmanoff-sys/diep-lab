"""Phase 24 — Production Cutover Automation DB integration test.

Exercises the real start_cutover -> validate_cutover -> fetch round-trip and the
audit trail against a live database (the part the mocked unit tests don't cover).
Infra probes are stubbed to deterministic results, so NO live infrastructure is
touched; only the additive evidence tables are written. Skips when no DB is
reachable (host/CI without a database), matching the smoke-test convention.

Run (in a container with DB_HOST set):  python -m pytest tests/test_deployment_integration.py -q
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

import deployment as dep  # noqa: E402
import readiness as readiness_service  # noqa: E402


def _db_up() -> bool:
    try:
        import common
        conn = common.get_conn()
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_up(), reason="no database reachable")


@pytest.fixture
def stub_probes(monkeypatch, tmp_path):
    """All infra probes deterministic PASS; backups dir is a fresh tmp file."""
    run_id = str(uuid.uuid4())
    ready = readiness_service.ReadinessRunResponse(
        run_id=run_id, checked_at=datetime.now(timezone.utc), status="PASS",
        score=95, pass_threshold=90, recommendation="ok", source="itest",
        tenant_id="default", summary={}, checks=[])
    monkeypatch.setattr(readiness_service, "run_readiness_assessment",
                        lambda cfg, previous_run=None: ready)
    monkeypatch.setattr(readiness_service, "fetch_latest_readiness_run", lambda: None)
    monkeypatch.setattr(readiness_service, "inspect_containers",
                        lambda names: {n: {"running": True, "status": "running",
                                           "restart_count": 0, "started_at": None} for n in names})
    monkeypatch.setattr(dep, "_http_get", lambda url, timeout: (
        200, '{"data":{"activeTargets":[{"health":"up","labels":{"job":"x"}}]}}'))
    monkeypatch.setattr(dep, "_reuse_readiness_check", lambda fn: readiness_service.ReadinessCheckResult(
        check_name="x", status="PASS", weight=10, score=10, message="ok"))
    (tmp_path / "diep.sql").write_text("-- dump")
    cfg = dep.load_deployment_config()
    cfg.backup_dir = str(tmp_path)
    return cfg, run_id


def test_full_cutover_go(stub_probes):
    cfg, run_id = stub_probes
    rec = dep.start_cutover(cfg, operator="itest-admin", change_ref="CHG-IT",
                            checklist=[{"item": "noc", "done": True}], notes="window")
    assert rec.status == "STARTED" and rec.deployment_status == "IN_PROGRESS"
    assert rec.pre_cutover["status"] == "PASS"
    assert rec.readiness_run_id == run_id

    rec2 = dep.validate_cutover(cfg, rec.deployment_id, operator="itest-admin")
    assert rec2.status == "VALIDATED" and rec2.deployment_status == "GO"
    assert rec2.validation_score == 100
    assert rec2.duration_seconds is not None

    fetched = dep.fetch_deployment(rec.deployment_id)
    assert fetched.deployment_status == "GO"
    assert fetched.evidence["deployment_report"]["validation_score"] == 100
    assert fetched.evidence["health_snapshots"]["post_cutover"]

    types = [e.event_type for e in dep.fetch_deployment_events(rec.deployment_id)]
    for required in ("CUTOVER_STARTED", "BASELINE_CAPTURED", "CHECKLIST_ITEM",
                     "PRE_CUTOVER_VALIDATED", "POST_CUTOVER_VALIDATED", "EVIDENCE_RECORDED"):
        assert required in types


def test_history_and_status(stub_probes):
    cfg, _ = stub_probes
    rec = dep.start_cutover(cfg, operator="itest-admin")
    dep.validate_cutover(cfg, rec.deployment_id, operator="itest-admin")
    hist = dep.fetch_deployment_history(limit=50)
    assert hist.total >= 1
    assert dep.fetch_latest_deployment() is not None


def test_failed_validation_is_no_go(stub_probes, monkeypatch):
    cfg, _ = stub_probes
    rec = dep.start_cutover(cfg, operator="itest-admin", change_ref="CHG-NOGO")
    # FastAPI /readyz probe down -> critical fail -> NO-GO
    monkeypatch.setattr(dep, "_http_get",
                        lambda url, timeout: (_ for _ in ()).throw(OSError("refused")))
    rec2 = dep.validate_cutover(cfg, rec.deployment_id, operator="itest-admin")
    assert rec2.status == "FAILED" and rec2.deployment_status == "NO_GO"
    assert "fastapi_readyz" in rec2.post_cutover["summary"]["critical_failures"]
