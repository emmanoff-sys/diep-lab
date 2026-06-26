"""services/cim/api.py -- route-level smoke test via FastAPI's TestClient
(in-process, no real port needed for the HTTP layer itself; underlying
mapping calls still hit the real DB over the docker network -- see
CIM_INTEROPERABILITY_REPORT.md for the full live deployment verification)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from services.cim.api import app  # noqa: E402
from services.cim.config import Settings  # noqa: E402

client = TestClient(app)
DEV_TOKEN = next(iter(Settings.api_keys().keys()))  # whatever the unscoped/dev token actually is
AUTH = {"Authorization": f"Bearer {DEV_TOKEN}"}


def test_health_returns_200_with_no_auth_required():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "UP"


def test_metrics_returns_200_or_503_with_no_auth_required():
    resp = client.get("/metrics")
    assert resp.status_code in (200, 503)


def test_resource_route_without_token_is_401():
    resp = client.get("/cim/meters")
    assert resp.status_code == 401


def test_resource_route_with_bogus_token_is_401():
    resp = client.get("/cim/meters", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_list_meters_with_valid_token_is_200_and_a_list():
    resp = client.get("/cim/meters", headers=AUTH)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_meter_detail_for_unknown_device_is_404():
    resp = client.get("/cim/meters/THIS-DEVICE-DOES-NOT-EXIST", headers=AUTH)
    assert resp.status_code == 404


def test_invalid_node_type_query_param_is_400():
    resp = client.get("/cim/connectivity-nodes?node_type=not-real", headers=AUTH)
    assert resp.status_code == 400


def test_invalid_since_timestamp_is_400():
    resp = client.get("/cim/measurement-values?since=garbage", headers=AUTH)
    assert resp.status_code == 400


def test_export_json_for_meters_is_200_with_expected_shape():
    resp = client.get("/cim/export/meters?format=json", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"objectType", "count", "items"}


def test_export_xml_for_meters_is_200_and_xml_content_type():
    resp = client.get("/cim/export/meters?format=xml", headers=AUTH)
    assert resp.status_code == 200
    assert "xml" in resp.headers["content-type"]


def test_export_unknown_object_type_is_404():
    resp = client.get("/cim/export/not-a-real-type", headers=AUTH)
    assert resp.status_code == 404


def test_export_object_not_in_requested_profile_is_400():
    resp = client.get("/cim/export/feeders?profile=metering", headers=AUTH)
    assert resp.status_code == 400


def test_every_list_route_responds_without_error():
    routes = (
        "/cim/end-devices", "/cim/meters", "/cim/assets", "/cim/customers",
        "/cim/service-points", "/cim/usage-points", "/cim/connectivity-nodes",
        "/cim/terminals", "/cim/transformers", "/cim/feeders", "/cim/measurements",
        "/cim/measurement-values",
    )
    for route in routes:
        resp = client.get(route, headers=AUTH)
        assert resp.status_code == 200, f"{route} -> {resp.status_code}: {resp.text[:200]}"


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
