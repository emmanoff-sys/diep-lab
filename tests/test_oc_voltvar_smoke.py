"""ADMS Phase 2 (OC-4) smoke tests — governed Volt/VAR dispatch.

Runs against the live FastAPI app in the default safe posture (controls flag off).
Verifies the DER command mapping, the band interlock, magnitude-based risk
classification (single-operator vs two-person), dry-run, and that live dispatch is
flag-gated. No live dispatch occurs here; the single-op-vs-two-person execute gate
(flag on) is validated against an isolated DB.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_oc_voltvar_smoke.py -q
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


def _tok(user, pass_env, default):
    s, b = _req("POST", "/auth/token", {"username": user, "password": _env(pass_env, default)}, token="")
    if s != 200 or not b:
        pytest.skip(f"{user} login unavailable")
    return b["access_token"]


def _vv(op, target, setpoint, mode="dry_run", override=False):
    params = {"setpoint_kw": setpoint}
    if override:
        params["override"] = True
    return _req("POST", "/controls/actions",
                {"action_type": "voltvar_dispatch", "target": target, "params": params,
                 "mode": mode, "reason": "oc4 test"}, token=op)


def test_voltvar_registered():
    s, body = _req("GET", "/controls/status")
    assert s == 200 and "voltvar_dispatch" in body["registered_action_types"]


def test_small_in_band_is_low_risk_with_command_mapping():
    s, a = _vv(_tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026"), "INV001", 5)
    assert s == 200 and a["risk"] == "low"
    cmd = a["preview"]["command"]
    assert cmd["command_type"] == "set_limit" and cmd["max_power_kw"] == 5


def _big_swing_setpoint(op, der="MG001"):
    """Probe a DER's current output, then choose an in-band setpoint a clear
    >MAX_STEP_KW swing away — deterministic regardless of telemetry freshness."""
    s, probe = _vv(op, der, 0)
    assert s == 200, "probe failed"
    cur = probe["preview"]["current_output_kw"]
    rated = probe["preview"]["rated_kw"]
    sp = (cur + 100.0) if cur <= rated / 2 else (cur - 100.0)
    return max(0.0, min(sp, rated)), der


def test_large_swing_is_high_risk():
    op = _tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    sp, der = _big_swing_setpoint(op)
    s, a = _vv(op, der, sp)
    assert s == 200 and a["risk"] == "high" and a["preview"]["rate_limited_high_risk"] is True


def test_out_of_band_blocked_then_override():
    op = _tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    s, _ = _vv(op, "INV001", 20)            # > rated 10 kW
    assert s == 409
    s, a = _vv(op, "INV001", 20, override=True)
    assert s == 200 and a["status"] == "PENDING"


def test_unknown_der_404():
    s, _ = _vv(_tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026"), "NOPE", 1)
    assert s == 404


def test_high_risk_two_person_then_flag_blocks_live():
    op = _tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    eng = _tok("engineer", "DIEP_ENGINEER_PASSWORD", "diep-engineer-2026")
    sp, der = _big_swing_setpoint(op)
    s, a = _vv(op, der, sp, mode="live")
    assert s == 200 and a["risk"] == "high"
    aid = a["action_id"]
    # requester cannot self-approve a high-risk action.
    s, _ = _req("POST", f"/controls/actions/{aid}/approve", {}, token=op)
    assert s == 403
    s, ap = _req("POST", f"/controls/actions/{aid}/approve", {"reason": "ok"}, token=eng)
    assert s == 200 and ap["approved_by"] == "engineer"
    s, _ = _req("POST", f"/controls/actions/{aid}/execute", token=op)
    assert s == 403   # flag off
