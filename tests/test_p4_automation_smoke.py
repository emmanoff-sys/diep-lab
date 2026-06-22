"""ADMS Phase 4 (P4-1) smoke tests — closed-loop automation engine (safe posture).

Runs against the live API in the default posture (automation flag OFF). Verifies the
status/policy surface, role gating, and that the engine is inert until explicitly
enabled. The recommend/auto proposal flow (flag on) is validated on an isolated DB.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_p4_automation_smoke.py -q
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

BASE = os.getenv("DIEP_API_BASE", "http://localhost:8000")


def _env(key, default):
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


def _api_up():
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


def test_status_safe_default():
    s, b = _req("GET", "/automation/status")
    assert s == 200
    assert b["automation_enabled"] is False        # OFF by default
    assert b["default_mode"] == "recommend"
    assert "noop" in b["registered_kinds"]


def test_flisr_policy_registered():
    # P4-2: the FLISR auto-mode policy is registered with the engine and seeded off.
    s, b = _req("GET", "/automation/status")
    assert s == 200 and "flisr" in b["registered_kinds"]
    s, p = _req("GET", "/automation/policies")
    fp = next((x for x in p["policies"] if x["policy_id"] == "flisr_auto"), None)
    assert fp is not None and fp["kind"] == "flisr"
    assert fp["enabled"] is False and fp["mode"] == "recommend"
    assert fp["bounds"].get("require_restores_all") is True


def test_policies_seeded_disabled():
    s, b = _req("GET", "/automation/policies")
    assert s == 200
    ids = {p["policy_id"] for p in b["policies"]}
    assert {"noop_auto", "flisr_auto", "voltvar_auto"} <= ids
    assert all(p["enabled"] is False and p["mode"] == "recommend" for p in b["policies"])


def test_tick_inert_when_disabled():
    s, b = _req("POST", "/automation/tick")
    assert s == 200 and b["ran"] is False           # master flag OFF => no evaluation


def test_tick_requires_privilege():
    tok = _tok("viewer", "DIEP_VIEWER_PASSWORD", "diep-viewer-2026")
    s, _ = _req("POST", "/automation/tick", token=tok)
    assert s == 403                                 # viewer cannot run the engine


def test_policy_toggle_requires_engineer():
    tok = _tok("operator", "DIEP_OPERATOR_PASSWORD", "diep-operator-2026")
    s, _ = _req("PATCH", "/automation/policies/noop_auto", {"enabled": True}, token=tok)
    assert s == 403                                 # operator cannot change policies
