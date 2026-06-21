"""ADMS M5 smoke tests — Historian query API + load forecasting.

Integration-style against the live FastAPI app. Seeds a few telemetry points for
BAT001 via the service token, then exercises the Historian query/retention API
and the load forecaster.

Run:  DIEP_API_BASE=http://diep-fastapi:8000 python -m pytest tests/test_historian_forecast_smoke.py -q
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

BASE = os.getenv("DIEP_API_BASE", "http://localhost:8000")


def _env(key: str, default: str) -> str:
    if os.getenv(key):
        return os.environ[key]
    envf = Path(__file__).resolve().parent.parent / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
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

SERVICE = _env("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")


@pytest.fixture(scope="module", autouse=True)
def _seed_history():
    now = datetime.now(timezone.utc)
    for i in range(8):
        _req("POST", "/telemetry", {
            "device_id": "BAT001",
            "time": (now - timedelta(minutes=5 * (8 - i))).isoformat(),
            "voltage": 230, "current": 40, "power_kw": 20 + i, "frequency": 50,
            "solar_kw": 0, "battery_soc": 60, "grid_import_kw": 20 + i, "grid_export_kw": 0,
        }, token=SERVICE)


def test_historian_query_raw():
    status, body = _req("GET", "/historian/query?device_id=BAT001&metric=power_kw&bucket=raw&hours=2")
    assert status == 200
    assert body["source"] == "telemetry"
    assert body["count"] >= 8


def test_historian_bad_metric_422():
    status, _ = _req("GET", "/historian/query?device_id=BAT001&metric=drop_table&bucket=raw")
    assert status == 422


def test_historian_retention_lists_policies():
    status, body = _req("GET", "/historian/retention")
    assert status == 200
    assert any(h["hypertable_name"] == "telemetry" for h in body["hypertables"])
    assert len(body["policies"]) >= 1


def test_forecast_load():
    status, body = _req("GET", "/forecast/load?device_id=BAT001&horizon_hours=6")
    assert status == 200
    assert len(body["forecast"]) == 6
    assert body["history_points"] >= 8
    assert all(p["forecast_kw"] >= 0 for p in body["forecast"])


def test_forecast_unknown_device_404():
    status, _ = _req("GET", "/forecast/load?device_id=NOPE")
    assert status == 404
