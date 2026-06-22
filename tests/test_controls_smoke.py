"""ADMS Phase 2 (OC-1) smoke tests — operational-controls governance core.

Integration-style against the live FastAPI app (sql/018 applied). Verifies the
governed lifecycle on the safe `noop` action type: RBAC gates, dry-run (works with
controls disabled), two-person approval, the OC_CONTROLS_ENABLED flag gating LIVE
actuation, and the append-only audit trail. Creates only `noop` records — no grid
or device actuation.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_controls_smoke.py -q
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


def _token(user_env, pass_env, default_pw):
    s, body = _req("POST", "/auth/token",
                   {"username": user_env, "password": _env(pass_env, default_pw)}, token="")
    if s != 200 or not body:
        pytest.skip(f"{user_env} login unavailable")
    return body["access_token"]


def test_status_disabled_by_default():
    status, body = _req("GET", "/controls/status")
    assert status == 200
    assert body["controls_enabled"] is False          # flag OFF by default
    assert body["default_mode"] == "dry_run"
    assert "noop" in body["registered_action_types"]


def test_viewer_cannot_request():
    vw = _token("viewer", "DIEP_VIEWER_PASSWORD", "diep-viewer-2026")
    status, _ = _req("POST", "/controls/actions", {"action_type": "noop"}, token=vw)
    assert status == 403


def test_dryrun_lifecycle_no_flag_needed():
    op = _token("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    s, a = _req("POST", "/controls/actions",
                {"action_type": "noop", "mode": "dry_run", "reason": "oc1 test"}, token=op)
    assert s == 200 and a["status"] == "PENDING"
    s, e = _req("POST", f"/controls/actions/{a['action_id']}/execute", token=op)
    assert s == 200 and e["status"] == "EXECUTED" and e.get("dry_run") is True


def test_operator_cannot_approve():
    op = _token("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    s, a = _req("POST", "/controls/actions", {"action_type": "noop"}, token=op)
    assert s == 200
    # operator is not in APPROVE_ROLES (engineer/admin only).
    s, _ = _req("POST", f"/controls/actions/{a['action_id']}/approve", {}, token=op)
    assert s == 403


def test_live_action_blocked_by_flag_and_audited():
    op = _token("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    eng = _token("engineer", "DIEP_ENGINEER_PASSWORD", "diep-engineer-2026")
    s, a = _req("POST", "/controls/actions",
                {"action_type": "noop", "mode": "live", "reason": "flag-gate"}, token=op)
    assert s == 200
    aid = a["action_id"]
    s, ap = _req("POST", f"/controls/actions/{aid}/approve", {"reason": "ok"}, token=eng)
    assert s == 200 and ap["status"] == "APPROVED" and ap["approved_by"] == "engineer"
    # live execute refused while OC_CONTROLS_ENABLED is off.
    s, _ = _req("POST", f"/controls/actions/{aid}/execute", token=op)
    assert s == 403
    # audit trail records the full sequence including the BLOCKED attempt.
    s, body = _req("GET", f"/controls/audit?action_id={aid}")
    assert s == 200
    events = [e["event"] for e in body["audit"]]
    assert events[:2] == ["REQUESTED", "APPROVED"] and "BLOCKED" in events
