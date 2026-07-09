"""WP-013-02 OA-061 — Operator API HTTP surface tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operator_fixtures import (  # noqa: E402
    NO_ROLE_TOKEN,
    VIEWER_TOKEN,
    auth_headers,
    experience_app,
)

from fastapi.testclient import TestClient


def _client(**kwargs) -> TestClient:
    app, _, _ = experience_app(**kwargs)
    return TestClient(app)


def test_dashboard_returns_versioned_envelope():
    client = _client(faulted=True)
    response = client.get("/api/v1/dashboard", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v1"
    assert payload["view"] == "dashboard"
    assert payload["data"]["platform"]["customers_affected"] == 40
    assert payload["data"]["platform"]["active_outage_groups"] == 1


def test_missing_token_is_401_and_bad_token_is_401():
    client = _client()
    no_token_response = client.get("/api/v1/dashboard")
    assert no_token_response.status_code == 401
    bad_token_response = client.get("/api/v1/dashboard", headers={"Authorization": "Bearer wrong"})
    assert bad_token_response.status_code == 401


def test_read_role_required_is_403():
    client = _client()
    response = client.get("/api/v1/dashboard", headers=auth_headers(NO_ROLE_TOKEN))
    assert response.status_code == 403


def test_viewer_role_can_read():
    client = _client()
    viewer_response = client.get("/api/v1/network", headers=auth_headers(VIEWER_TOKEN))
    assert viewer_response.status_code == 200


def test_asset_endpoints_and_unknown_asset_404():
    client = _client(faulted=True)
    found = client.get("/api/v1/assets/e1", headers=auth_headers())
    assert found.status_code == 200
    assert found.json()["data"]["available"] is False
    missing = client.get("/api/v1/assets/zz", headers=auth_headers())
    assert missing.status_code == 404
    search = client.get("/api/v1/assets/search", params={"q": "tie"}, headers=auth_headers())
    assert [item["asset_id"] for item in search.json()["data"]] == ["tie1"]


def test_topology_explorer_endpoint():
    client = _client()
    response = client.get("/api/v1/topology/b", headers=auth_headers())
    assert response.status_code == 200
    assert [edge["edge_id"] for edge in response.json()["data"]["edges"]] == [
        "e2",
        "sw1",
        "tie1",
    ]
    not_found_response = client.get("/api/v1/topology/zz", headers=auth_headers())
    assert not_found_response.status_code == 404


def test_recommendations_endpoint_contract():
    client = _client(faulted=True)
    response = client.get("/api/v1/recommendations", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    workspace = data[0]
    assert set(workspace) == {
        "group_id",
        "outage",
        "fault_candidates",
        "strategies",
        "explanations",
        "rule_outcomes",
    }
    assert workspace["strategies"][0]["tie_edge_id"] == "tie1"
    assert workspace["fault_candidates"][0]["edge_id"] == "e1"


def test_history_endpoints_with_filters():
    client = _client(faulted=True, seed_audit=True)
    everything = client.get("/api/v1/history", headers=auth_headers())
    assert everything.json()["data"]["record_count"] == 3
    filtered = client.get(
        "/api/v1/history", params={"kind": "plan_generated"}, headers=auth_headers()
    )
    assert filtered.json()["data"]["record_count"] == 1
    recommendations = client.get("/api/v1/history/recommendations", headers=auth_headers())
    assert recommendations.json()["data"]["record_count"] == 1
    record_id = recommendations.json()["data"]["records"][0]["record_id"]
    trace = client.get(f"/api/v1/history/{record_id}/trace", headers=auth_headers())
    assert trace.status_code == 200
    assert len(trace.json()["data"]) == 3
    bad_trace_response = client.get("/api/v1/history/decision:999999/trace", headers=auth_headers())
    assert bad_trace_response.status_code == 404


def test_timeline_endpoint():
    client = _client(faulted=True, seed_audit=True)
    response = client.get("/api/v1/timeline", params={"asset_id": "e1"}, headers=auth_headers())
    assert response.status_code == 200
    sources = [entry["source"] for entry in response.json()["data"]]
    assert "state" in sources


def test_api_is_read_only_by_construction():
    app, _, _ = experience_app()
    methods = {
        method for route in app.routes if hasattr(route, "methods") for method in route.methods
    }
    assert "POST" not in methods
    assert "PUT" not in methods
    assert "PATCH" not in methods
    assert "DELETE" not in methods
    client = TestClient(app)
    post_response = client.post("/api/v1/dashboard", headers=auth_headers())
    assert post_response.status_code == 405
