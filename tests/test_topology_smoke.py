"""ADMS M1 smoke tests — Unified Network Model API.

Integration-style: exercises the live FastAPI topology router (sql/013 must be
applied and the fastapi service running). Reads the admin API key from
DIEP_ADMIN_KEY (or .env) and the base URL from DIEP_API_BASE
(default http://localhost:8000). Skips cleanly if the API is unreachable.

Run:  DIEP_API_BASE=http://localhost:8000 python -m pytest tests/test_topology_smoke.py -q
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE = os.getenv("DIEP_API_BASE", "http://localhost:8000")


def _admin_key() -> str:
    key = os.getenv("DIEP_ADMIN_KEY")
    if key:
        return key
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DIEP_ADMIN_KEY="):
                return line.split("=", 1)[1].strip()
    return "diep-admin-dev-key-CHANGE-ME"


def _req(method, path, body=None, token=_admin_key()):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _api_up() -> bool:
    try:
        urllib.request.urlopen(BASE + "/healthz", timeout=3)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason=f"DIEP API not reachable at {BASE}")


def test_unauthenticated_read_rejected():
    status, _ = _req("GET", "/topology/version", token=None)
    assert status in (401, 403)


def test_current_version():
    status, body = _req("GET", "/topology/version")
    assert status == 200 and body["version"] >= 1


def test_graph_has_seeded_model():
    status, body = _req("GET", "/topology/graph")
    assert status == 200
    assert len(body["nodes"]) >= 9 and len(body["edges"]) >= 8


def test_downstream_finds_affected_customers():
    status, body = _req("GET", "/topology/downstream/FDR-01")
    assert status == 200
    assert body["affected_customer_count"] >= 3
    assert "ND-METER001" in body["meter_nodes"]


def test_open_switch_severs_downstream_then_restore():
    # Opening the sectionalizing switch must de-energize the LV bus subtree.
    s, _ = _req("PATCH", "/topology/edges/E-SW-01/switch", {"is_closed": False})
    assert s == 200
    try:
        _, body = _req("GET", "/topology/downstream/FDR-01")
        assert body["affected_customer_count"] == 0
    finally:
        s2, _ = _req("PATCH", "/topology/edges/E-SW-01/switch", {"is_closed": True})
        assert s2 == 200


def test_node_crud_and_conflict():
    _req("DELETE", "/topology/nodes/PYTEST-ND")  # best-effort pre-clean
    s, body = _req("POST", "/topology/nodes",
                   {"node_id": "PYTEST-ND", "node_type": "load", "name": "pytest"})
    assert s == 201 and body["node_id"] == "PYTEST-ND"
    s_dup, _ = _req("POST", "/topology/nodes", {"node_id": "PYTEST-ND", "node_type": "load"})
    assert s_dup == 409
    s_del, _ = _req("DELETE", "/topology/nodes/PYTEST-ND")
    assert s_del == 200


def test_non_switchable_edge_rejected():
    s, _ = _req("PATCH", "/topology/edges/E-SUB-FDR/switch", {"is_closed": False})
    assert s == 409  # E-SUB-FDR is a line, not switchable
