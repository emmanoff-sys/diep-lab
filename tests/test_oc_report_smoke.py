"""ADMS Phase 2 (OC-6) smoke tests — operational audit & safety reporting.

Runs against the live FastAPI app in the default safe posture (controls flag off).
Verifies the readiness snapshot, filtered history + aggregates, the CSV audit
export, the Prometheus control-plane metrics, and read-role gating. Read-only:
these tests request a dry-run noop only to populate a deterministic audit event.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_oc_report_smoke.py -q
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


def _req(method, path, body=None, token=None, raw=False):
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
            payload = resp.read()
            if raw:
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, payload.decode(), hdrs
            return resp.status, json.loads(payload or "null")
    except urllib.error.HTTPError as exc:
        return (exc.code, None, {}) if raw else (exc.code, None)


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


def test_readiness_shape_and_posture():
    s, b = _req("GET", "/controls/report/readiness")
    assert s == 200
    # default safe posture: flag off.
    assert b["controls_enabled"] is False and b["posture"] == "SAFE"
    for key in ("counts", "activity_24h", "warnings", "registered_action_types",
                "awaiting_approval", "ready"):
        assert key in b
    assert {"flisr", "switch_op", "voltvar_dispatch", "noop"} <= set(b["registered_action_types"])
    for st in ("PENDING", "APPROVED", "EXECUTED", "FAILED", "ROLLED_BACK"):
        assert st in b["counts"]


def test_dryrun_then_reflected_in_history_and_counts():
    # request + execute a dry-run noop; it must appear in history aggregates.
    s, a = _req("POST", "/controls/actions",
                {"action_type": "noop", "params": {"oc6": "test"}, "mode": "dry_run", "reason": "oc6"})
    assert s == 200
    aid = a["action_id"]
    s, _ = _req("POST", f"/controls/actions/{aid}/execute")
    assert s == 200
    s, h = _req("GET", "/controls/report/history?action_type=noop&since_hours=24&limit=500")
    assert s == 200 and h["total"] >= 1
    assert "noop" in h["summary"]["by_action_type"]
    assert h["summary"]["by_mode"].get("dry_run", 0) >= 1


def test_history_filters():
    s, h = _req("GET", "/controls/report/history?status=EXECUTED&since_hours=168&limit=50")
    assert s == 200
    assert all(x["status"] == "EXECUTED" for x in h["actions"])


def test_audit_export_csv():
    s, text, headers = _req("GET", "/controls/audit/export?format=csv&since_hours=48", raw=True)
    assert s == 200
    assert "text/csv" in headers.get("content-type", "")
    assert "attachment" in headers.get("content-disposition", "")
    header = text.splitlines()[0]
    assert header.startswith("at,action_id,action_type,risk,mode,target,event,actor")


def test_metrics_exposes_control_plane():
    s, text, _ = _req("GET", "/metrics", raw=True)
    assert s == 200
    assert "diep_control_events_total" in text
    assert "diep_controls_enabled" in text
    assert "diep_control_actions" in text


def test_readiness_readable_by_viewer():
    tok = _tok("viewer", "DIEP_VIEWER_PASSWORD", "diep-viewer-2026")
    s, b = _req("GET", "/controls/report/readiness", token=tok)
    assert s == 200 and b["posture"] in ("SAFE", "LIVE")


def test_history_rejects_anonymous():
    s, _ = _req("GET", "/controls/report/history", token="")
    assert s in (401, 403)
