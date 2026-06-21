"""ADMS M2 smoke tests — Outage Management System.

Integration-style against the live FastAPI app (sql/013+014 applied). Exercises
the OMS lifecycle through the API only: a customer call creates+confirms a case
(resolving affected customers via the M1 topology), KPIs reflect it, the public
endpoint is reachable without auth and exposes no PII, then the case is closed.

Reuses the same helpers/skip logic as test_topology_smoke.py.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_oms_smoke.py -q
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


def _close_all_open():
    _, body = _req("GET", "/oms/cases")
    for c in (body or {}).get("cases", []):
        if c["status"] != "CLOSED":
            _req("PATCH", f"/oms/cases/{c['case_id']}", {"status": "CLOSED"})


def test_public_outages_open_and_no_pii():
    status, body = _req("GET", "/oms/public/outages", token=None)  # no auth
    assert status == 200
    assert "outages" in body and "customers_affected" in body
    # public payload must not leak caller/customer identity fields.
    blob = json.dumps(body).lower()
    assert "caller_phone" not in blob and "caller_name" not in blob


def test_call_handler_creates_and_confirms_case():
    _close_all_open()
    status, body = _req("POST", "/oms/call", {
        "customer_id": "CUST-001", "caller_name": "pytest caller",
        "caller_phone": "+234-000", "description": "no power"})
    assert status == 201
    assert body["report"]["status"] == "LINKED"
    case_id = body["report"]["case_id"]
    assert case_id
    s, case = _req("GET", f"/oms/cases/{case_id}")
    assert s == 200
    assert case["status"] == "CONFIRMED"            # a corroborated case is confirmed
    assert case["customers_affected"] >= 1          # resolved via M1 topology
    assert any(r["caller_name"] == "pytest caller" for r in case["reports"])


def test_kpis_present():
    status, body = _req("GET", "/oms/kpis?window_hours=24")
    assert status == 200
    for key in ("call_volume", "active_outages", "customers_impacted",
                "saidi_minutes", "saifi", "total_service_points"):
        assert key in body


def test_manual_case_and_close():
    s, case = _req("POST", "/oms/cases", {"affected_node_id": "TX-01", "notes": "pytest"})
    assert s == 201 and case["status"] == "CONFIRMED"
    s2, closed = _req("PATCH", f"/oms/cases/{case['case_id']}", {"status": "CLOSED"})
    assert s2 == 200 and closed["status"] == "CLOSED" and closed["closed_at"] is not None
    _close_all_open()


def test_detect_is_idempotent_callable():
    s, body = _req("POST", "/oms/detect")
    assert s == 200
    assert set(body).issuperset({"created", "updated", "restored", "signals"})
    _close_all_open()
