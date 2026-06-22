"""ADMS Phase 3 (P3-1) smoke tests — the DNP3 RTU MGD900 is governable.

Verifies the data wiring (migration 019) that brings the RTU under the Phase-2
governed control plane with no handler changes: it is a controllable microgrid
DER (OC-4 voltvar_dispatch) and its grid-tie breaker is a device-backed switchable
edge (OC-2 switch_op -> island/grid_connect). All checks are dry-run/read-only in
the default safe posture (controls flag off); nothing actuates.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_p3_rtu_governable.py -q
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE = os.getenv("DIEP_API_BASE", "http://localhost:8000")
RTU = "MGD900"
BREAKER = "E-MGD900-CB"


def _env(key: str, default: str) -> str:
    if os.getenv(key):
        return os.environ[key]
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return default


def _req(method, path, body=None, token=None):
    if token is None:
        token = _env("DIEP_ADMIN_KEY", "diep-admin-dev-key-CHANGE-ME")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def test_rtu_is_controllable_der():
    s, b = _req("GET", "/der/assets")
    assert s == 200
    rtu = next((d for d in b["der_assets"] if d["der_id"] == RTU), None)
    assert rtu is not None, "MGD900 not registered as a DER"
    assert rtu["der_type"] == "microgrid" and rtu["controllable"] is True


def test_rtu_breaker_is_switchable_device_backed_edge():
    s, g = _req("GET", "/topology/graph")
    assert s == 200
    edge = next((e for e in g["edges"] if e["edge_id"] == BREAKER), None)
    assert edge is not None, "E-MGD900-CB breaker edge missing"
    assert edge["edge_type"] == "switch" and edge["is_switchable"] is True


def test_switch_op_dryrun_reaches_rtu_breaker():
    # open the breaker = island the RTU; device-backed, high-risk, no interlock hit.
    s, a = _req("POST", "/controls/actions",
                {"action_type": "switch_op", "target": BREAKER, "params": {"close": False},
                 "mode": "dry_run", "reason": "p3 test"})
    assert s == 200
    assert a["risk"] == "high"
    assert a["preview"]["device_backed"] is True
    assert a["preview"]["edge"] == BREAKER


def test_voltvar_dryrun_reaches_rtu_setpoint():
    s, a = _req("POST", "/controls/actions",
                {"action_type": "voltvar_dispatch", "target": RTU, "params": {"setpoint_kw": 50},
                 "mode": "dry_run", "reason": "p3 test"})
    assert s == 200
    # microgrid setpoint maps to the DNP3 analog-output command.
    assert a["preview"]["command"]["command_type"] == "set_setpoint"
    assert a["preview"]["rated_kw"] == 250.0


def test_rtu_setpoint_banded_to_rating():
    s, _ = _req("POST", "/controls/actions",
                {"action_type": "voltvar_dispatch", "target": RTU, "params": {"setpoint_kw": 999},
                 "mode": "dry_run", "reason": "p3 band"})
    assert s == 409  # 999 kW exceeds the 250 kW rating; blocked unless overridden
