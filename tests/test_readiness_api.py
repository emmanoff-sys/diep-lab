import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = ROOT / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import app as diep_app  # noqa: E402
import readiness  # noqa: E402
from routers import controls as controls_router  # noqa: E402

client = TestClient(diep_app.app)
pytestmark = pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:DeprecationWarning"
)


def _sample_run() -> readiness.ReadinessRunResponse:
    return readiness.ReadinessRunResponse(
        run_id="run-1",
        checked_at=datetime(2026, 6, 23, 14, 9, 43, tzinfo=timezone.utc),
        status="FAIL",
        score=90,
        pass_threshold=90,
        recommendation="FAIL — keep MW2 blocked until uptime reaches 24 hours",
        source="scripts/run_mw2_readiness_check.py",
        tenant_id="default",
        summary={"checks_failed": 1, "minimum_uptime_seconds": 4740},
        checks=[
            readiness.ReadinessCheckResult(
                check_name="critical_service_uptime",
                status="FAIL",
                weight=10,
                score=0,
                message="uptime below threshold",
                observed={"uptime_seconds": {"diep-kafka": 4740}},
                threshold={"minimum_seconds": 86400},
            )
        ],
    )


def test_readiness_endpoint_returns_latest_run(monkeypatch):
    monkeypatch.setattr(controls_router.readiness_service, "fetch_latest_readiness_run", lambda: _sample_run())
    monkeypatch.setattr(controls_router.readiness_service, "refresh_prometheus_metrics", lambda: None)
    response = client.get(
        "/controls/readiness",
        headers={"Authorization": "Bearer diep-admin-dev-key-CHANGE-ME"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-1"
    assert body["status"] == "FAIL"
    assert body["checks"][0]["check_name"] == "critical_service_uptime"


def test_readiness_history_returns_summaries(monkeypatch):
    history = readiness.ReadinessHistoryResponse(
        total=1,
        limit=50,
        since_hours=168,
        status=None,
        runs=[
            readiness.ReadinessRunSummary(
                run_id="run-1",
                checked_at=datetime(2026, 6, 23, 14, 9, 43, tzinfo=timezone.utc),
                status="FAIL",
                score=90,
                pass_threshold=90,
                recommendation="hold",
                source="pytest",
                tenant_id="default",
                summary={"checks_failed": 1},
            )
        ],
    )
    monkeypatch.setattr(
        controls_router.readiness_service,
        "fetch_readiness_history",
        lambda limit=50, since_hours=168, status=None: history,
    )
    response = client.get(
        "/controls/readiness/history",
        headers={"Authorization": "Bearer diep-admin-dev-key-CHANGE-ME"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["runs"][0]["run_id"] == "run-1"


def test_readiness_endpoint_rejects_operator_role():
    response = client.get(
        "/controls/readiness",
        headers={"Authorization": "Bearer diep-operator-dev-key-CHANGE-ME"},
    )
    assert response.status_code == 403
