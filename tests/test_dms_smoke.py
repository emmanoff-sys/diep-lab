"""ADMS M3 smoke tests — Distribution Management System (DMS).

Integration-style against the live FastAPI app (sql/013+015 applied). Verifies
state estimation, the FLISR isolate+restore plan (without mutating switch state),
and Volt/VAR output. Reuses the helper/skip pattern of the other smoke tests.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_dms_smoke.py -q
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
        with urllib.request.urlopen(req, timeout=8) as resp:
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


def _edge_closed(edge_id: str) -> bool:
    _, body = _req("GET", "/topology/edges")
    return next(e["is_closed"] for e in body["edges"] if e["edge_id"] == edge_id)


def test_state_estimation_shape():
    status, body = _req("GET", "/dms/state_estimation")
    assert status == 200
    assert body["total_nodes"] >= 10
    n = body["nodes"][0]
    assert "estimated_voltage_pu" in n and "monitored" in n and "energized" in n


def test_flisr_plan_isolates_and_restores_without_mutating():
    assert _edge_closed("E-SW-01") is True
    assert _edge_closed("E-TIE-01") is False
    status, body = _req("POST", "/dms/flisr/simulate", {"fault_node": "TX-01", "execute": False})
    assert status == 200
    assert body["isolated_edges"] == ["E-SW-01"]
    assert body["restored_edges"] == ["E-TIE-01"]   # back-feed BUS-01 via the tie
    assert body["customers_restored"] >= 3
    assert body["executed"] is False
    # plan-only must not have changed live switch state.
    assert _edge_closed("E-SW-01") is True
    assert _edge_closed("E-TIE-01") is False


def test_flisr_requires_fault():
    status, _ = _req("POST", "/dms/flisr/simulate", {"execute": False})
    assert status == 422


def test_voltvar_shape():
    status, body = _req("GET", "/dms/voltvar/recommendations")
    assert status == 200
    assert "recommendations" in body and "bands" in body
