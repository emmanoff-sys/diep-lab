"""Phase 24 — Production Cutover Automation API tests (TestClient, mocked service).

Run:  python -m pytest tests/test_deployment_api.py -q
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = ROOT / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import app as diep_app  # noqa: E402
import deployment as deployment_service  # noqa: E402

client = TestClient(diep_app.app)
pytestmark = pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:DeprecationWarning"
)

ADMIN = {"Authorization": "Bearer diep-admin-dev-key-CHANGE-ME"}
OPERATOR = {"Authorization": "Bearer diep-operator-dev-key-CHANGE-ME"}
SERVICE = {"Authorization": "Bearer diep-service-dev-token-CHANGE-ME"}


def _sample_record(deployment_id="dep-1", gate="GO", status="VALIDATED"):
    return deployment_service.DeploymentRecord(
        deployment_id=deployment_id,
        started_at=datetime(2026, 6, 23, 1, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 6, 23, 1, 12, 0, tzinfo=timezone.utc),
        status=status, deployment_status=gate, operator="api-admin",
        validation_score=100, pass_threshold=90, duration_seconds=720.0,
    )


def test_status_returns_latest(monkeypatch):
    monkeypatch.setattr(deployment_service, "fetch_latest_deployment", lambda: _sample_record())
    monkeypatch.setattr(deployment_service, "refresh_prometheus_metrics", lambda: None)
    r = client.get("/deployment/status", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["latest"]["deployment_id"] == "dep-1"
    assert body["latest"]["deployment_status"] == "GO"
    assert body["pre_cutover_now"] is None


def test_status_rejects_operator():
    r = client.get("/deployment/status", headers=OPERATOR)
    assert r.status_code == 403


def test_history_returns_summaries(monkeypatch):
    hist = deployment_service.DeploymentHistoryResponse(
        total=1, limit=50, since_hours=720, status=None,
        runs=[deployment_service.DeploymentSummary(
            deployment_id="dep-1",
            started_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            status="VALIDATED", deployment_status="GO", operator="api-admin",
            pass_threshold=90, validation_score=100)])
    monkeypatch.setattr(deployment_service, "fetch_deployment_history",
                        lambda limit=50, since_hours=720, status=None: hist)
    r = client.get("/deployment/history", headers=SERVICE)
    assert r.status_code == 200
    assert r.json()["runs"][0]["deployment_id"] == "dep-1"


def test_cutover_start_admin(monkeypatch):
    captured = {}

    def fake_start(config, operator, change_ref, checklist, notes):
        captured.update(operator=operator, change_ref=change_ref, checklist=checklist)
        return _sample_record(deployment_id="dep-2", gate="IN_PROGRESS", status="STARTED")

    monkeypatch.setattr(deployment_service, "start_cutover", fake_start)
    r = client.post("/deployment/cutover/start", headers=ADMIN, json={
        "change_ref": "CHG-42",
        "checklist": [{"item": "notify NOC", "done": True}],
        "notes": "window 02:00-04:00"})
    assert r.status_code == 200
    assert r.json()["deployment_id"] == "dep-2"
    assert captured["operator"] == "api-admin"
    assert captured["change_ref"] == "CHG-42"
    assert captured["checklist"][0]["item"] == "notify NOC"


def test_cutover_start_rejects_operator():
    r = client.post("/deployment/cutover/start", headers=OPERATOR, json={})
    assert r.status_code == 403


def test_status_live_runs_pre_cutover(monkeypatch):
    pre = deployment_service.ValidationResult(
        phase="pre_cutover", status="PASS", score=100, pass_threshold=90,
        checked_at=datetime(2026, 6, 23, tzinfo=timezone.utc), checks=[], summary={})
    monkeypatch.setattr(deployment_service, "fetch_latest_deployment", lambda: None)
    monkeypatch.setattr(deployment_service, "refresh_prometheus_metrics", lambda: None)
    monkeypatch.setattr(deployment_service, "load_deployment_config", lambda: object())
    monkeypatch.setattr(deployment_service, "run_pre_cutover_validation", lambda cfg: (pre, None))
    r = client.get("/deployment/status?live=true", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["pre_cutover_now"]["status"] == "PASS"


def test_status_db_unavailable_returns_503(monkeypatch):
    import psycopg2

    def boom():
        raise psycopg2.OperationalError("down")
    monkeypatch.setattr(deployment_service, "fetch_latest_deployment", boom)
    r = client.get("/deployment/status", headers=ADMIN)
    assert r.status_code == 503


def test_validate_no_inflight_returns_404(monkeypatch):
    empty = deployment_service.DeploymentHistoryResponse(
        total=0, limit=1, since_hours=720, status="STARTED", runs=[])
    monkeypatch.setattr(deployment_service, "load_deployment_config", lambda: object())
    monkeypatch.setattr(deployment_service, "fetch_deployment_history",
                        lambda limit=1, since_hours=720, status=None: empty)
    r = client.post("/deployment/cutover/validate", headers=ADMIN, json={})
    assert r.status_code == 404


def test_validate_unknown_id_returns_404(monkeypatch):
    monkeypatch.setattr(deployment_service, "load_deployment_config", lambda: object())

    def boom(config, deployment_id, operator):
        raise KeyError(deployment_id)
    monkeypatch.setattr(deployment_service, "validate_cutover", boom)
    r = client.post("/deployment/cutover/validate", headers=ADMIN, json={"deployment_id": "nope"})
    assert r.status_code == 404


def test_history_db_unavailable_returns_503(monkeypatch):
    import psycopg2

    def boom(limit=50, since_hours=720, status=None):
        raise psycopg2.OperationalError("down")
    monkeypatch.setattr(deployment_service, "fetch_deployment_history", boom)
    r = client.get("/deployment/history", headers=SERVICE)
    assert r.status_code == 503


def test_cutover_validate_defaults_to_latest_started(monkeypatch):
    hist = deployment_service.DeploymentHistoryResponse(
        total=1, limit=1, since_hours=720, status="STARTED",
        runs=[deployment_service.DeploymentSummary(
            deployment_id="dep-3",
            started_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            status="STARTED", deployment_status="IN_PROGRESS", operator="api-admin",
            pass_threshold=90)])
    seen = {}

    def fake_validate(config, deployment_id, operator):
        seen.update(deployment_id=deployment_id, operator=operator)
        return _sample_record(deployment_id=deployment_id)

    monkeypatch.setattr(deployment_service, "fetch_deployment_history",
                        lambda limit=1, since_hours=720, status=None: hist)
    monkeypatch.setattr(deployment_service, "validate_cutover", fake_validate)
    r = client.post("/deployment/cutover/validate", headers=ADMIN, json={})
    assert r.status_code == 200
    assert seen["deployment_id"] == "dep-3"
    assert r.json()["deployment_status"] == "GO"
