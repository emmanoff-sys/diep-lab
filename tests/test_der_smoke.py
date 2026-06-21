"""ADMS M4 smoke tests — DERMS layer (DER registry + aggregation + dispatch).

Integration-style against the live FastAPI app (sql/013+016 applied). Covers the
registry, fleet aggregation, dispatch validation, and the multi-tenancy fix
(tenant-scoped principal blocked from another tenant's DER). Successful dispatch
to Kafka is validated manually (it produces commands), kept out of the repeatable
suite to stay side-effect-free.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_der_smoke.py -q
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


def test_fleet_aggregate():
    status, body = _req("GET", "/der/fleet")
    assert status == 200
    assert body["der_count"] >= 4
    assert body["total_rated_kw"] > 0
    assert "battery" in body["by_type"]


def test_registry_lists_ders_bound_to_nodes():
    status, body = _req("GET", "/der/assets")
    assert status == 200
    ids = {a["der_id"]: a for a in body["der_assets"]}
    assert "BAT001" in ids and ids["BAT001"]["node_id"] == "ND-BAT001"


def test_dispatch_unknown_der_404():
    status, _ = _req("POST", "/der/dispatch", {"der_id": "NOPE", "command_type": "discharge"})
    assert status == 404


def test_curtail_unknown_der_404():
    status, _ = _req("POST", "/der/curtailment", {"der_id": "NOPE", "limit_kw": 1})
    assert status == 404


def test_tenant_isolation_blocks_cross_tenant_dispatch():
    # acme-op (tenant=acme) must not dispatch BAT001 (tenant=default) — the
    # multi-tenancy gap the legacy /derms endpoints had, closed in /der.
    s, body = _req("POST", "/auth/token",
                   {"username": "acme-op", "password": _env("DIEP_ACME_PASSWORD", "acme-2026")}, token="")
    if s != 200 or not body:
        pytest.skip("acme-op login unavailable")
    tok = body["access_token"]
    status, _ = _req("POST", "/der/dispatch", {"der_id": "BAT001", "command_type": "discharge"}, token=tok)
    assert status == 403
