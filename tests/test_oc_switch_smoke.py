"""ADMS Phase 2 (OC-2) smoke tests — governed switch operations.

Runs against the live FastAPI app with controls in the default safe posture
(OC_CONTROLS_ENABLED off). Verifies the plan-time interlocks, dry-run planning,
the no-op guard, override behaviour, and that LIVE switch actuation is refused
while the flag is off. No live switch actuation occurs (the model is never
mutated here); live execute + rollback are validated separately against an
isolated DB.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_oc_switch_smoke.py -q
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE = os.getenv("DIEP_API_BASE", "http://localhost:8000")


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


def _op():
    s, b = _req("POST", "/auth/token",
                {"username": "operator", "password": _env("DIEP_OPERATOR_PASSWORD", "diep-operator-2026")}, token="")
    if s != 200 or not b:
        pytest.skip("operator login unavailable")
    return b["access_token"]


def _eng():
    s, b = _req("POST", "/auth/token",
                {"username": "engineer", "password": _env("DIEP_ENGINEER_PASSWORD", "diep-engineer-2026")}, token="")
    if s != 200 or not b:
        pytest.skip("engineer login unavailable")
    return b["access_token"]


def _request_switch(op, target, close, mode="dry_run", override=False, reason="oc2 test"):
    params = {"close": close}
    if override:
        params["override"] = True
    return _req("POST", "/controls/actions",
                {"action_type": "switch_op", "target": target, "params": params,
                 "mode": mode, "reason": reason}, token=op)


def test_switch_op_registered():
    s, body = _req("GET", "/controls/status")
    assert s == 200 and "switch_op" in body["registered_action_types"]


def test_open_critical_switch_blocked_by_islanding_interlock():
    # opening E-SW-01 de-energizes the section with the medical customer.
    s, _ = _request_switch(_op(), "E-SW-01", close=False)
    assert s == 409


def test_close_tie_blocked_by_paralleling_interlock():
    # E-TIE-01 closed would tie two already-energized sources.
    s, _ = _request_switch(_op(), "E-TIE-01", close=True)
    assert s == 409


def test_noop_blocked():
    s, _ = _request_switch(_op(), "E-SW-01", close=True)  # already closed
    assert s == 409


def test_safe_switch_dryrun_does_not_actuate():
    op = _op()
    s, a = _request_switch(op, "E-SW-02", close=False, mode="dry_run")
    assert s == 200 and a["risk"] == "high" and a["preview"]["customers_lost"] == 0
    s, e = _req("POST", f"/controls/actions/{a['action_id']}/execute", token=op)
    assert s == 200 and e.get("dry_run") is True
    # the live model state must be unchanged by a dry-run.
    s, edges = _req("GET", "/topology/edges")
    sw02 = next(x for x in edges["edges"] if x["edge_id"] == "E-SW-02")
    assert sw02["is_closed"] is True


def test_override_bypasses_interlock_but_records_it():
    s, a = _request_switch(_op(), "E-SW-01", close=False, override=True, reason="maint; medical notified")
    assert s == 200
    assert a["preview"]["interlocks"] and a["preview"]["overridden"] is True


def test_live_switch_blocked_by_flag():
    op, eng = _op(), _eng()
    s, a = _request_switch(op, "E-SW-02", close=False, mode="live")
    assert s == 200
    aid = a["action_id"]
    s, ap = _req("POST", f"/controls/actions/{aid}/approve", {"reason": "ok"}, token=eng)
    assert s == 200 and ap["approved_by"] == "engineer"   # two-person path
    s, _ = _req("POST", f"/controls/actions/{aid}/execute", token=op)
    assert s == 403   # OC_CONTROLS_ENABLED is off
