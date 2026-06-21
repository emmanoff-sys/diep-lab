"""ADMS Phase 2 (OC-3) smoke tests — governed FLISR execution.

Runs against the live FastAPI app in the default safe posture (controls flag off).
Verifies the governed `flisr` planner/preview, that dry-run does not actuate, the
"won't re-energize the fault" safety case, that live execution is flag-gated, and
that the legacy ungoverned /dms/flisr/simulate execute=true path is now gated too.
No live actuation occurs; execute + rollback are validated against an isolated DB.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_oc_flisr_smoke.py -q
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


def _flisr(op, target, mode="dry_run"):
    return _req("POST", "/controls/actions",
                {"action_type": "flisr", "target": target, "mode": mode, "reason": "oc3 test"}, token=op)


def test_flisr_registered():
    s, body = _req("GET", "/controls/status")
    assert s == 200 and "flisr" in body["registered_action_types"]


def test_flisr_plan_preview():
    s, a = _flisr(_tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026"), "TX-01")
    assert s == 200 and a["risk"] == "high"
    p = a["preview"]
    assert p["isolated_edges"] == ["E-SW-01"] and p["restored_edges"] == ["E-TIE-01"]
    assert p["customers_restored"] >= 3 and p["restores_all"] is True


def test_flisr_dryrun_does_not_actuate():
    op = _tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    s, a = _flisr(op, "TX-01")
    assert s == 200
    s, e = _req("POST", f"/controls/actions/{a['action_id']}/execute", token=op)
    assert s == 200 and e.get("dry_run") is True
    s, edges = _req("GET", "/topology/edges")
    st = {x["edge_id"]: x["is_closed"] for x in edges["edges"]}
    assert st["E-SW-01"] is True and st["E-TIE-01"] is False   # untouched


def test_flisr_safety_refuses_to_reenergize_fault():
    # fault on the bus: the only tie would re-energize the faulted node -> refused.
    s, a = _flisr(_tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026"), "BUS-01")
    assert s == 200
    assert a["preview"]["restored_edges"] == [] and a["preview"]["restores_all"] is False


def test_flisr_live_blocked_by_flag():
    op = _tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    eng = _tok("engineer", "DIEP_ENGINEER_PASSWORD", "diep-engineer-2026")
    s, a = _flisr(op, "TX-01", mode="live")
    assert s == 200
    aid = a["action_id"]
    s, ap = _req("POST", f"/controls/actions/{aid}/approve", {"reason": "ok"}, token=eng)
    assert s == 200 and ap["approved_by"] == "engineer"
    s, _ = _req("POST", f"/controls/actions/{aid}/execute", token=op)
    assert s == 403


def test_legacy_dms_execute_true_now_flag_gated():
    # ungoverned direct mutation path is closed unless OC_CONTROLS_ENABLED.
    s, _ = _req("POST", "/dms/flisr/simulate", {"fault_node": "TX-01", "execute": True})
    assert s == 403
