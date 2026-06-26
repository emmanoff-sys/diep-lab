"""fastapi/app.py's GET /telemetry/latest -- auth + tenant-scoping regression
tests (RC remediation sprint, closing the P0 finding in GO_LIVE_CHECKLIST.md
that this route had no auth dependency at all).

Route-level test via FastAPI's TestClient (in-process, no real port needed
for the HTTP layer itself; the underlying query still hits the real DB over
the docker network -- same shape as tests/test_cim_api.py, the closest
precedent in this repo for testing a FastAPI app's auth boundary)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
import auth  # noqa: E402

client = TestClient(app)

ADMIN_TOKEN = auth.issue_jwt("test-admin", "admin")
SIT_TENANT_TOKEN = auth.issue_jwt("test-sit", "operator", tenant="sit-tenant")
SIT_TENANT_B_TOKEN = auth.issue_jwt("test-sit-b", "operator", tenant="sit-tenant-b")
ACME_TOKEN = auth.issue_jwt("test-acme", "operator", tenant="acme")  # real account, zero real devices


def _device_tenant(device_id: str) -> str | None:
    """Look up a device's real tenant directly, so tests verify against the
    database's own ground truth rather than trusting the response."""
    import psycopg2
    conn = psycopg2.connect(**auth._DB)
    cur = conn.cursor()
    cur.execute("SELECT tenant_id FROM devices WHERE device_id = %s", (device_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def test_no_token_is_401():
    resp = client.get("/telemetry/latest")
    assert resp.status_code == 401


def test_bogus_token_is_401():
    resp = client.get("/telemetry/latest", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_global_admin_token_sees_latest_overall():
    resp = client.get("/telemetry/latest", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "message" not in body  # real data exists in this environment


def test_sit_tenant_token_only_sees_its_own_tenant():
    resp = client.get("/telemetry/latest", headers={"Authorization": f"Bearer {SIT_TENANT_TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "message" not in body
    assert _device_tenant(body["device_id"]) == "sit-tenant"


def test_sit_tenant_b_token_never_leaks_sit_tenant_data():
    """The actual cross-tenant-leak regression test: a sit-tenant-b-scoped
    caller must never see sit-tenant's (much larger) dataset."""
    resp = client.get("/telemetry/latest", headers={"Authorization": f"Bearer {SIT_TENANT_B_TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "message" not in body
    tenant = _device_tenant(body["device_id"])
    assert tenant == "sit-tenant-b"
    assert tenant != "sit-tenant"


def test_tenant_with_no_devices_gets_empty_not_someone_elses_data():
    """acme-op exists as a real authenticated account but the 'acme' tenant
    has zero devices/telemetry in this environment -- must get the polite
    empty response, never another tenant's row."""
    resp = client.get("/telemetry/latest", headers={"Authorization": f"Bearer {ACME_TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"message": "No telemetry found"}
