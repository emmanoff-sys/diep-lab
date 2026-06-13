"""DIEP Digital Twin service.

A lightweight aggregation + presentation layer that builds a live "digital twin"
of every asset by composing data the DIEP API already exposes:

  registry identity   ← GET /assets , GET /assets/{id}
  live runtime state  ← current_state (Redis-backed) inside the asset record
  asset spec/metadata ← asset_metadata inside the asset record
  health verdict      ← GET /health/assets , GET /assets/{id}/health
  command history     ← GET /commands?device_id=...
  maintenance insight ← GET /analytics/predictive_maintenance (detail view only)

It serves both a browser dashboard (HTML) and a JSON API:

  GET /                      → redirect to /twins
  GET /twins                 → HTML dashboard (grid of twin cards)
  GET /twins/{device_id}     → HTML detail page for one twin
  GET /api/twins             → JSON list of all twins
  GET /api/twins/{device_id} → JSON single twin
  GET /health                → service health

The service holds no database of its own — the DIEP API remains the source of
truth. Configure the upstream with DIEP_API_BASE.
"""
import os
import html
import logging

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("diep-twins")

DIEP_API_BASE = os.getenv("DIEP_API_BASE", "http://diep-fastapi:8000")
HTTP_TIMEOUT = float(os.getenv("DIEP_API_TIMEOUT", "5"))
REFRESH_SECONDS = int(os.getenv("TWIN_REFRESH_SECONDS", "10"))

app = FastAPI(title="DIEP Digital Twin", docs_url="/docs", openapi_url="/openapi.json")

# Per-type "headline" metrics surfaced prominently on each twin card. Each entry
# is (label, source_key). Keys are looked up first in live_state (canonical
# telemetry fields populated by the ingestor), then in asset_metadata — so a
# device shows its spec values (capacity, max power) before telemetry flows and
# its live readings once it does.
HEADLINE_METRICS = {
    "battery": [("SOC %", "battery_soc"), ("Power kW", "power_kw"),
                ("Capacity kWh", "capacity_kwh")],
    "solar_inverter": [("Solar kW", "solar_kw"), ("Power kW", "power_kw"),
                       ("Capacity kW", "capacity_kw")],
    "ev_charger": [("Power kW", "power_kw"), ("Voltage", "voltage"),
                   ("Max kW", "max_power_kw")],
    "microgrid": [("Frequency Hz", "frequency"), ("Power kW", "power_kw"),
                  ("Solar kW", "solar_kw")],
    "smartmeter": [("Power kW", "power_kw"), ("Voltage", "voltage"),
                   ("Solar kW", "solar_kw"), ("Frequency Hz", "frequency")],
}

HEALTH_COLORS = {
    "OK": "#1f9d55",
    "DEGRADED": "#d97706",
    "OFFLINE": "#b91c1c",
    "UNKNOWN": "#6b7280",
}


# --- Upstream DIEP API access ----------------------------------------------
def _api_get(path: str, params: dict | None = None):
    url = f"{DIEP_API_BASE}{path}"
    resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _safe_api_get(path: str, params: dict | None = None, default=None):
    """Best-effort GET that never raises — used for enrichment that should not
    fail the whole twin if one upstream call is unavailable."""
    try:
        return _api_get(path, params)
    except requests.RequestException as exc:
        logger.warning("Upstream GET %s failed: %s", path, exc)
        return default


# --- Twin assembly ----------------------------------------------------------
def _twin_from_asset(asset: dict, health: dict, last_command: dict | None) -> dict:
    """Compose a twin object from an asset record + health + last command."""
    return {
        "device_id": asset.get("device_id"),
        "device_type": asset.get("device_type"),
        "site_name": asset.get("site_name"),
        "location": asset.get("location"),
        "registry_status": asset.get("status"),
        "health": health or {"health": "UNKNOWN", "reason": "No health data"},
        "live_state": asset.get("current_state") or {},
        "asset_metadata": asset.get("asset_metadata") or {},
        "last_command": last_command,
    }


def _headline(twin: dict) -> list[dict]:
    """Resolve the per-type headline metrics for a twin, skipping absent values."""
    state = twin.get("live_state") or {}
    meta = twin.get("asset_metadata") or {}
    out = []
    for label, key in HEADLINE_METRICS.get(twin["device_type"], []):
        value = state.get(key, meta.get(key))
        if value is None:
            continue
        out.append({"label": label, "value": value})
    return out


def build_all_twins() -> list[dict]:
    """Build twins for every registered asset using a fixed number of upstream
    calls (3 total) regardless of fleet size."""
    assets = _api_get("/assets").get("assets", [])

    health_rows = _safe_api_get("/health/assets", default={"assets": []}).get("assets", [])
    health_by_id = {row["device_id"]: row.get("health", {}) for row in health_rows}

    commands = _safe_api_get("/commands", {"limit": 200}, default={"commands": []}).get("commands", [])
    last_cmd_by_id: dict[str, dict] = {}
    for cmd in commands:  # /commands returns newest-first; keep the first per device
        last_cmd_by_id.setdefault(cmd["device_id"], cmd)

    return [
        _twin_from_asset(a, health_by_id.get(a["device_id"], {}), last_cmd_by_id.get(a["device_id"]))
        for a in assets
    ]


def build_twin(device_id: str, include_analytics: bool = False) -> dict:
    try:
        asset = _api_get(f"/assets/{device_id}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Unknown twin '{device_id}'")
        raise HTTPException(status_code=502, detail=f"Upstream DIEP API error: {exc}")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"DIEP API unreachable: {exc}")

    health = _safe_api_get(f"/assets/{device_id}/health", default={})
    commands = _safe_api_get("/commands", {"device_id": device_id, "limit": 10},
                             default={"commands": []}).get("commands", [])
    twin = _twin_from_asset(asset, health, commands[0] if commands else None)
    twin["recent_commands"] = commands
    if include_analytics:
        twin["maintenance"] = _safe_api_get(
            "/analytics/predictive_maintenance", {"device_id": device_id})
    return twin


# --- JSON API ---------------------------------------------------------------
@app.get("/api/twins")
def api_twins():
    return {"twins": build_all_twins()}


@app.get("/api/twins/{device_id}")
def api_twin(device_id: str):
    return build_twin(device_id, include_analytics=True)


@app.get("/health")
def health():
    upstream = "UP"
    try:
        _api_get("/health")
    except requests.RequestException:
        upstream = "DOWN"
    return {"status": "UP", "service": "digital-twin", "diep_api": upstream}


# --- HTML rendering ---------------------------------------------------------
def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:g}"
    return _esc(value)


def _health_badge(health: dict) -> str:
    label = (health.get("health") or "UNKNOWN").upper()
    color = HEALTH_COLORS.get(label, HEALTH_COLORS["UNKNOWN"])
    return f'<span class="badge" style="background:{color}">{_esc(label)}</span>'


PAGE_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       background:#0f1419; color:#e6e6e6; }
header { padding:20px 28px; border-bottom:1px solid #232a33;
         display:flex; align-items:baseline; gap:14px; }
header h1 { margin:0; font-size:20px; }
header .sub { color:#8b95a1; font-size:13px; }
header a { color:#5aa9e6; text-decoration:none; }
.wrap { padding:24px 28px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }
.card { background:#161b22; border:1px solid #232a33; border-radius:10px; padding:16px;
        text-decoration:none; color:inherit; display:block; transition:border-color .15s; }
.card:hover { border-color:#3b82f6; }
.card .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
.card .id { font-size:16px; font-weight:600; }
.card .type { color:#8b95a1; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
.card .site { color:#8b95a1; font-size:12px; margin-bottom:12px; }
.badge { display:inline-block; padding:2px 9px; border-radius:999px; color:#fff;
         font-size:11px; font-weight:600; letter-spacing:.03em; }
.metrics { display:grid; grid-template-columns:1fr 1fr; gap:8px 14px; margin-top:6px; }
.metric .k { color:#8b95a1; font-size:11px; }
.metric .v { font-size:15px; font-weight:600; }
.cmd { margin-top:12px; padding-top:10px; border-top:1px solid #232a33; font-size:12px; color:#8b95a1; }
table { width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }
th,td { text-align:left; padding:6px 10px; border-bottom:1px solid #232a33; }
th { color:#8b95a1; font-weight:600; }
.section { background:#161b22; border:1px solid #232a33; border-radius:10px; padding:18px; margin-bottom:18px; }
.section h2 { margin:0 0 10px; font-size:15px; }
.empty { color:#8b95a1; font-style:italic; }
.back { color:#5aa9e6; text-decoration:none; font-size:13px; }
"""


def _page(title: str, body: str, auto_refresh: bool = True) -> str:
    refresh = f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">' if auto_refresh else ""
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh}<title>{_esc(title)}</title><style>{PAGE_CSS}</style></head><body>{body}</body></html>"""


def _card(twin: dict) -> str:
    metrics = "".join(
        f'<div class="metric"><div class="k">{_esc(m["label"])}</div>'
        f'<div class="v">{_fmt(m["value"])}</div></div>'
        for m in _headline(twin)
    ) or '<div class="empty">No live metrics yet</div>'

    cmd = twin.get("last_command")
    cmd_html = (
        f'<div class="cmd">Last command: <b>{_esc(cmd["command_type"])}</b> '
        f'&middot; {_esc(cmd["status"])}</div>'
        if cmd else '<div class="cmd">No commands issued</div>'
    )
    return f"""<a class="card" href="/twins/{_esc(twin['device_id'])}">
  <div class="top"><span class="id">{_esc(twin['device_id'])}</span>{_health_badge(twin['health'])}</div>
  <div class="type">{_esc(twin['device_type'])}</div>
  <div class="site">{_esc(twin.get('site_name') or twin.get('location') or '—')}</div>
  <div class="metrics">{metrics}</div>
  {cmd_html}
</a>"""


def render_dashboard(twins: list[dict]) -> str:
    cards = "".join(_card(t) for t in twins) or '<div class="empty">No assets registered.</div>'
    body = f"""<header><h1>DIEP Digital Twins</h1>
<span class="sub">{len(twins)} assets &middot; live from DIEP API &middot; auto-refresh {REFRESH_SECONDS}s</span></header>
<div class="wrap"><div class="grid">{cards}</div></div>"""
    return _page("DIEP Digital Twins", body)


def _kv_table(data: dict) -> str:
    if not data:
        return '<div class="empty">No data</div>'
    rows = "".join(
        f"<tr><td>{_esc(k)}</td><td>{_fmt(v)}</td></tr>" for k, v in data.items()
    )
    return f"<table><tr><th>Field</th><th>Value</th></tr>{rows}</table>"


def render_detail(twin: dict) -> str:
    headline = "".join(
        f'<div class="metric"><div class="k">{_esc(m["label"])}</div>'
        f'<div class="v">{_fmt(m["value"])}</div></div>'
        for m in _headline(twin)
    ) or '<div class="empty">No live metrics yet</div>'

    cmds = twin.get("recent_commands") or []
    if cmds:
        cmd_rows = "".join(
            f"<tr><td>{_esc(c.get('command_type'))}</td><td>{_esc(c.get('status'))}</td>"
            f"<td>{_esc(c.get('created_at'))}</td></tr>"
            for c in cmds
        )
        cmd_table = f"<table><tr><th>Command</th><th>Status</th><th>Created</th></tr>{cmd_rows}</table>"
    else:
        cmd_table = '<div class="empty">No commands issued</div>'

    maint = twin.get("maintenance")
    maint_html = ""
    if maint:
        reasons = maint.get("reasons") or []
        reason_list = ("<ul>" + "".join(f"<li>{_esc(r)}</li>" for r in reasons) + "</ul>"
                       if reasons else '<div class="empty">No risk factors detected</div>')
        maint_html = f"""<div class="section"><h2>Predictive Maintenance</h2>
        <p>Severity: <b>{_esc(maint.get('severity'))}</b> &middot; score {_esc(maint.get('score'))}</p>
        {reason_list}</div>"""

    h = twin["health"]
    body = f"""<header><h1>{_esc(twin['device_id'])}</h1>
<span class="sub">{_esc(twin['device_type'])} &middot; {_esc(twin.get('site_name') or '—')}</span>
<span class="sub"><a class="back" href="/twins">&larr; all twins</a></span></header>
<div class="wrap">
  <div class="section"><h2>Status {_health_badge(h)}</h2>
    <p class="sub">{_esc(h.get('reason') or '')}</p>
    <div class="metrics">{headline}</div></div>
  <div class="section"><h2>Live State</h2>{_kv_table(twin.get('live_state'))}</div>
  <div class="section"><h2>Asset Metadata</h2>{_kv_table(twin.get('asset_metadata'))}</div>
  <div class="section"><h2>Recent Commands</h2>{cmd_table}</div>
  {maint_html}
</div>"""
    return _page(f"Twin · {twin['device_id']}", body)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/twins")


@app.get("/twins", response_class=HTMLResponse)
def twins_dashboard():
    try:
        twins = build_all_twins()
    except requests.RequestException as exc:
        logger.error("Failed to build dashboard: %s", exc)
        body = (f'<div class="wrap"><div class="section"><h2>DIEP API unreachable</h2>'
                f'<p class="sub">{_esc(exc)}</p></div></div>')
        return HTMLResponse(_page("DIEP Digital Twins", body, auto_refresh=True), status_code=503)
    return HTMLResponse(render_dashboard(twins))


@app.get("/twins/{device_id}", response_class=HTMLResponse)
def twin_detail(device_id: str):
    twin = build_twin(device_id, include_analytics=True)
    return HTMLResponse(render_detail(twin))
