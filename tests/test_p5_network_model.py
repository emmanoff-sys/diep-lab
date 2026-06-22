"""ADMS P5-M1 smoke tests — Network Model Service (electrical model + validation).

Integration-style (same harness as test_topology_smoke): exercises the live
topology router with sql/021 applied. Verifies the new electrical attributes,
topology validation (loop detection / radiality / hierarchy), adjacency, and the
recloser node type. Skips cleanly if the API is unreachable.

Run:  DIEP_API_BASE=http://localhost:8000 python -m pytest tests/test_p5_network_model.py -q
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


def test_edges_carry_electrical_params():
    status, body = _req("GET", "/topology/graph")
    assert status == 200
    by_id = {e["edge_id"]: e for e in body["edges"]}
    line = by_id["E-BUS-METER"]
    assert line["resistance_r_ohm"] is not None and line["reactance_x_ohm"] is not None
    assert line["ampacity_a"] is not None
    # the EV lateral is modeled single-phase (unbalance scenario)
    assert by_id["E-BUS-EV"]["phases"] == "A"


def test_nodes_carry_base_load_and_phases():
    status, body = _req("GET", "/topology/nodes/ND-METER001")
    assert status == 200
    assert body["base_load_kw"] and float(body["base_load_kw"]) > 0
    assert body["phases"] == "ABC"
    s_ev, ev = _req("GET", "/topology/nodes/ND-EV001")
    assert s_ev == 200 and ev["phases"] == "A"


def test_validate_seeded_model_is_radial_and_ok():
    status, body = _req("GET", "/topology/validate")
    assert status == 200
    assert body["ok"] is True
    assert body["radial"] is True
    assert body["operational_loops"] == 0
    assert body["orphan_nodes"] == []
    # the normally-open tie is structurally a loop the model knows about
    assert body["structural_loops"] >= 1
    assert "E-TIE-01" in body["loop_closing_switches"]


def test_closing_tie_creates_operational_loop_then_restore():
    # Closing the normally-open tie while the primary path is closed forms a loop;
    # validation must flag non-radial operation. Restore afterwards.
    s, _ = _req("PATCH", "/topology/edges/E-TIE-01/switch", {"is_closed": True})
    assert s == 200
    try:
        _, body = _req("GET", "/topology/validate")
        assert body["operational_loops"] >= 1
        assert body["radial"] is False
        assert body["ok"] is False  # parallel feed / loop is an error
    finally:
        s2, _ = _req("PATCH", "/topology/edges/E-TIE-01/switch", {"is_closed": False})
        assert s2 == 200


def test_adjacency_components():
    status, body = _req("GET", "/topology/adjacency")
    assert status == 200
    assert body["component_count"] >= 1
    assert "BUS-01" in body["adjacency"]


def test_recloser_node_type_accepted():
    _req("DELETE", "/topology/nodes/PYTEST-REC")  # best-effort pre-clean
    s, body = _req("POST", "/topology/nodes",
                   {"node_id": "PYTEST-REC", "node_type": "recloser", "name": "pytest recloser",
                    "phases": "ABC"})
    assert s == 201 and body["node_type"] == "recloser"
    s_del, _ = _req("DELETE", "/topology/nodes/PYTEST-REC")
    assert s_del == 200
