"""WP-006-05 — API tests for the version history & diff endpoints.

Same harness pattern as tests/test_topology_publish_api.py: the live
FastAPI app driven by TestClient, with common.query_one/query_all
monkeypatched to serve canned rows — no live Postgres required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
FASTAPI_DIR = ROOT / "fastapi"
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

import app as diep_app  # noqa: E402
import common  # noqa: E402

client = TestClient(diep_app.app)

ADMIN = {"Authorization": "Bearer diep-admin-dev-key-CHANGE-ME"}

V1 = {"version": 1, "label": "initial", "description": None, "created_by": "system",
      "is_current": False, "created_at": "2026-07-01T00:00:00+00:00"}
V2 = {"version": 2, "label": "import-2", "description": None, "created_by": "api-admin",
      "is_current": False, "created_at": "2026-07-07T00:00:00+00:00"}
V3 = {"version": 3, "label": "import-3", "description": None, "created_by": "api-admin",
      "is_current": True, "created_at": "2026-07-08T00:00:00+00:00"}


class FakeDb:
    """Serves canned answers keyed by SQL fragment, recording every query."""

    def __init__(self, versions: list[dict], nodes: list[dict], edges: list[dict]):
        self.versions = versions
        self.nodes = nodes
        self.edges = edges
        self.queries: list[tuple[str, tuple]] = []

    def query_one(self, sql: str, params: tuple = ()):
        self.queries.append((sql, params))
        if "COUNT(*)" in sql and "network_model_versions" in sql:
            return {"n": len(self.versions)}
        if "COUNT(*)" in sql and "grid_nodes" in sql:
            return {"n": sum(1 for n in self.nodes if n["model_version"] == params[0])}
        if "COUNT(*)" in sql and "grid_edges" in sql:
            return {"n": sum(1 for e in self.edges if e["model_version"] == params[0])}
        if "SELECT 1 FROM network_model_versions" in sql:
            known = any(v["version"] == params[0] for v in self.versions)
            return {"?column?": 1} if known else None
        if "FROM network_model_versions WHERE version = " in sql:
            return next((v for v in self.versions if v["version"] == params[0]), None)
        raise AssertionError(f"unexpected query_one: {sql}")

    def query_all(self, sql: str, params: tuple):
        # No default for `params`: every router call site passes one, and a
        # `()` default would flow a provably-empty tuple into the 2-variable
        # unpacks below (CodeQL py/mismatched-multiple-assignment).
        self.queries.append((sql, params))
        if "FROM network_model_versions" in sql and "ORDER BY version DESC" in sql:
            ordered = sorted(self.versions, key=lambda v: -v["version"])
            limit, offset = params
            return ordered[offset:offset + limit]
        if "FROM network_model_versions" in sql and "version > " in sql:
            lo, hi = params
            return [v for v in sorted(self.versions, key=lambda v: v["version"])
                    if lo < v["version"] <= hi]
        if "FROM grid_nodes" in sql:
            lo, hi = params
            return [n for n in self.nodes if lo < n["model_version"] <= hi]
        if "FROM grid_edges" in sql:
            lo, hi = params
            return [e for e in self.edges if lo < e["model_version"] <= hi]
        raise AssertionError(f"unexpected query_all: {sql}")


@pytest.fixture
def db(monkeypatch):
    fake = FakeDb(
        versions=[V1, V2, V3],
        nodes=[
            {"node_id": "SUB-01", "node_type": "substation", "name": None,
             "site_name": None, "model_version": 1},
            {"node_id": "BUS-01", "node_type": "bus", "name": None,
             "site_name": None, "model_version": 2},
            {"node_id": "BUS-02", "node_type": "bus", "name": None,
             "site_name": None, "model_version": 3},
        ],
        edges=[
            {"edge_id": "E-01", "from_node": "SUB-01", "to_node": "BUS-01",
             "edge_type": "line", "is_closed": True, "model_version": 2},
        ],
    )
    monkeypatch.setattr(common, "query_one", fake.query_one)
    monkeypatch.setattr(common, "query_all", fake.query_all)
    return fake


# --- history list ---------------------------------------------------------------
def test_versions_list_newest_first(db):
    r = client.get("/topology/versions", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert [v["version"] for v in body["versions"]] == [3, 2, 1]


def test_versions_list_pagination(db):
    r = client.get("/topology/versions?limit=1&offset=1", headers=ADMIN)
    body = r.json()
    assert [v["version"] for v in body["versions"]] == [2]
    assert body["limit"] == 1 and body["offset"] == 1


def test_versions_list_requires_auth(db):
    assert client.get("/topology/versions").status_code == 401


# --- single version -------------------------------------------------------------
def test_get_version_with_stamped_counts(db):
    r = client.get("/topology/versions/2", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["label"] == "import-2"
    assert body["nodes_stamped"] == 1 and body["edges_stamped"] == 1
    assert body["semantics"] == "write-stamp"


def test_get_unknown_version_404(db):
    r = client.get("/topology/versions/99", headers=ADMIN)
    assert r.status_code == 404


# --- diff -----------------------------------------------------------------------
def test_diff_reports_write_stamp_rows_in_range(db):
    r = client.get("/topology/versions/diff?from_version=1&to_version=3", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["semantics"] == "write-stamp"
    assert body["from_version"] == 1 and body["to_version"] == 3
    assert [v["version"] for v in body["versions_in_range"]] == [2, 3]
    assert {n["node_id"] for n in body["nodes"]} == {"BUS-01", "BUS-02"}
    assert [e["edge_id"] for e in body["edges"]] == ["E-01"]
    by_version = {v["version"]: v for v in body["versions_in_range"]}
    assert by_version[2]["nodes_touched"] == 1 and by_version[2]["edges_touched"] == 1
    assert by_version[3]["nodes_touched"] == 1 and by_version[3]["edges_touched"] == 0


def test_diff_inverted_range_422(db):
    r = client.get("/topology/versions/diff?from_version=3&to_version=1", headers=ADMIN)
    assert r.status_code == 422
    assert any("must be lower than" in e for e in r.json()["detail"]["errors"])


def test_diff_unknown_version_404(db):
    r = client.get("/topology/versions/diff?from_version=1&to_version=99", headers=ADMIN)
    assert r.status_code == 404


def test_diff_path_not_captured_by_version_route(db):
    """Route-order guard: /versions/diff must reach the diff handler, not
    422 as a non-integer {version} path parameter."""
    r = client.get("/topology/versions/diff?from_version=1&to_version=2", headers=ADMIN)
    assert r.status_code == 200
