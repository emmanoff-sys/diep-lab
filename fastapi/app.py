import os
import json
import time
import uuid
import socket
import statistics
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException, Response, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
import psycopg2.extras
from kafka import KafkaProducer
from kafka.errors import KafkaError
import redis
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

import auth
from auth import require_role, rate_limit
from redis_client import get_redis_client
# ADMS refactor: DB helpers live in common.py so routers/ can reuse them without
# importing app.py (which would be a cycle, since app.py mounts the routers).
from common import get_conn, DB_CONFIG
from routers.topology import router as topology_router
from routers.oms import router as oms_router
from routers.dms import router as dms_router
from routers.der import router as der_router
from routers.historian import router as historian_router
from routers.forecasting import router as forecasting_router
from routers.controls import router as controls_router

app = FastAPI(
    title="DIEP API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Phase 11A — CORS for the mobile/PWA clients. Token-based auth (Bearer), so
# credentials are off and any configured origin is allowed (set DIEP_CORS_ORIGINS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("DIEP_CORS_ORIGINS", "*").split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 21 — stamps X-Request-ID on every request/response and makes it
# available to auth.audit() automatically, for audit/API request correlation.
app.add_middleware(auth.RequestIDMiddleware)

# ADMS M1 — Unified Network Model (grid topology) API.
app.include_router(topology_router)
# ADMS M2 — Outage Management System (OMS) API.
app.include_router(oms_router)
# ADMS M3 — Distribution Management System (DMS) API.
app.include_router(dms_router)
# ADMS M4 — DERMS layer: DER registry + aggregation + dispatch.
app.include_router(der_router)
# ADMS M5 — Historian query API + short-term load forecasting.
app.include_router(historian_router)
app.include_router(forecasting_router)
# ADMS Phase 2 (OC-1) — operational-controls governance core (flag-gated actuation).
app.include_router(controls_router)


@app.get("/version")
def version():
    return {"platform": "DIEP", "api_version": "v1", "app_version": app.version,
            "build": os.getenv("DIEP_BUILD", "dev")}

# DB_CONFIG/get_conn moved to common.py (imported above) during the ADMS refactor.

# Phase 9J-S5 — default to the authenticated SASL listener (9094). Env-overridable.
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "diep-kafka:9094")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT")
KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "diep")
# Phase 22 SEC-2 — no hardcoded credential; must come from .env (KAFKA_SASL_PASSWORD).
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "change-me-kafka-sasl-password")


def _kafka_security_kwargs():
    """SASL/TLS connection kwargs for kafka-python, when not plain PLAINTEXT."""
    if KAFKA_SECURITY_PROTOCOL == "PLAINTEXT":
        return {}
    kw = {"security_protocol": KAFKA_SECURITY_PROTOCOL}
    if "SASL" in KAFKA_SECURITY_PROTOCOL:
        kw.update(sasl_mechanism=KAFKA_SASL_MECHANISM,
                  sasl_plain_username=KAFKA_SASL_USERNAME,
                  sasl_plain_password=KAFKA_SASL_PASSWORD)
    return kw


COMMAND_TOPIC = "diep.commands"

# device_type -> set of command_types accepted by that asset class.
# Unknown device types are allowed through (no allowlist enforced) so new
# asset classes can be wired up before their command vocabulary is finalised.
ALLOWED_COMMANDS = {
    "ev_charger": {"start_charging", "stop_charging", "set_limit"},
    "battery": {"charge", "discharge", "set_soc_target", "idle", "set_power_limit", "standby"},
    "solar_inverter": {"curtail", "set_limit", "resume"},
    "microgrid": {"island", "grid_connect", "set_setpoint"},
    "smartmeter": {"read_only", "remote_disconnect", "remote_connect"},
}

# Phase 9-Data: InfluxDB retired from the API path — TimescaleDB is the authoritative
# telemetry store. (A legacy Node-RED flow still writes an Influx 'smartmeter' measurement;
# remove that node to fully decommission Influx.)

REDIS = get_redis_client()


# --- Phase 9J: authentication -------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(..., examples=["operator"])
    password: str = Field(..., examples=["diep-operator-2026"])


@app.post("/auth/token")
def login(body: LoginRequest):
    """Exchange username/password for a short-lived access JWT + a refresh token (mobile)."""
    result = auth.authenticate_user(body.username, body.password)
    if result is None:
        auth.audit(None, "login", body.username, "denied")
        raise HTTPException(status_code=401, detail="invalid credentials")
    role, tenant, token_version = result
    auth.audit(auth.Principal(body.username, role, "jwt", tenant=tenant), "login", body.username, "ok")
    return {
        "access_token": auth.issue_jwt(body.username, role, tenant=tenant, token_version=token_version),
        "refresh_token": auth.issue_refresh(body.username, role, tenant=tenant, token_version=token_version),
        "token_type": "bearer",
        "role": role,
        "tenant": tenant,
        "expires_in": auth.JWT_TTL,
    }


class RefreshRequest(BaseModel):
    refresh_token: str


@app.post("/auth/refresh")
def refresh_token(body: RefreshRequest):
    """Exchange a valid refresh token for a new short-lived access token."""
    payload = auth.verify_jwt(body.refresh_token, expected_use="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="invalid or expired refresh token")
    return {
        "access_token": auth.issue_jwt(payload["sub"], payload["role"],
                                       tenant=payload.get("tenant"),
                                       token_version=payload.get("tv", 0)),
        "token_type": "bearer",
        "role": payload["role"],
        "tenant": payload.get("tenant"),
        "expires_in": auth.JWT_TTL,
    }


@app.get("/auth/whoami")
def whoami(principal=Depends(require_role("viewer", "operator", "engineer", "admin", "service"))):
    """Return the caller's authenticated identity (handy for debugging RBAC)."""
    return {"principal": principal.name, "role": principal.role, "auth": principal.kind}


@app.post("/auth/logout")
def logout(request: Request,
          principal=Depends(require_role("viewer", "operator", "engineer", "admin", "service"))):
    """Revokes the presented access token's jti server-side (Redis), so a stolen
    or cached token cannot be replayed after logout — not just 'client forgets it'."""
    revoked = False
    if principal.kind == "jwt" and principal.token:
        revoked = auth.revoke_token(principal.token)
    auth.audit(principal, "logout", principal.name, "ok" if revoked else "noop")
    return {"status": "logged_out", "revoked": revoked}


class PasswordResetRequest(BaseModel):
    username: str = Field(..., examples=["operator"])


@app.post("/auth/password-reset/request")
def password_reset_request(body: PasswordResetRequest,
                           _rl=Depends(rate_limit("password-reset", 5, 300))):
    """Issues a 15-minute single-use reset token.

    Lab/demo limitation: this stack has no outbound email/SMS integration (see
    alertmanager/alertmanager.yml's placeholder webhook receivers for the same
    gap on the ops-alerting side), so the token is returned directly in this
    response rather than delivered out-of-band. Wire this to a real mailer
    before production and stop returning the token here.
    """
    token = auth.request_password_reset(body.username)
    auth.audit(None, "password_reset_requested", body.username, "ok" if token else "unknown_user")
    # Always 202 regardless of whether the user exists, to avoid username enumeration
    # via response-shape difference; the token field is simply absent if unknown.
    resp = {"status": "accepted"}
    if token:
        resp["reset_token"] = token
        resp["expires_in"] = auth.RESET_TTL
    return resp


class PasswordResetConfirm(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=12)


@app.post("/auth/password-reset/confirm")
def password_reset_confirm(body: PasswordResetConfirm):
    ok = auth.confirm_password_reset(body.reset_token, body.new_password)
    auth.audit(None, "password_reset_completed", "(token)", "ok" if ok else "invalid_token")
    if not ok:
        raise HTTPException(status_code=400, detail="invalid or expired reset token")
    return {"status": "password_updated"}


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=12)
    role: str = Field(..., examples=["operator"])
    tenant: str | None = None


@app.post("/auth/users", status_code=201)
def create_user(body: CreateUserRequest, principal=Depends(require_role("admin"))):
    try:
        auth.create_user(body.username, body.password, body.role, body.tenant)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=409, detail=f"user '{body.username}' already exists")
    auth.audit(principal, "create_user", body.username, "ok", {"role": body.role, "tenant": body.tenant})
    return {"username": body.username, "role": body.role, "tenant": body.tenant}


@app.get("/auth/users")
def get_users(principal=Depends(require_role("admin"))):
    return {"users": auth.list_users()}


@app.delete("/auth/users/{username}")
def remove_user(username: str, principal=Depends(require_role("admin"))):
    auth.delete_user(username)
    auth.audit(principal, "delete_user", username, "ok")
    return {"status": "deleted", "username": username}


@app.get("/audit/events")
def get_audit_events(principal: str | None = None, action: str | None = None,
                     since: str | None = None, limit: int = 50, offset: int = 0,
                     _p=Depends(require_role("admin"))):
    """Read surface for audit_events (Phase 21 — closes the prior no-UI/API gap)."""
    limit = min(max(limit, 1), 200)
    return {"events": auth.list_audit_events(principal, action, since, limit, offset)}


# --- Phase 9K: orchestration health probes (open; used by LB + k8s) -----------
_INSTANCE = os.getenv("HOSTNAME", "fastapi")


@app.get("/healthz")
def healthz():
    """Liveness: process is up. No dependency checks (never flaps the LB on a
    transient DB blip). Returns the serving instance so HA/round-robin is visible."""
    return {"status": "ok", "instance": _INSTANCE}


@app.get("/readyz")
def readyz():
    """Readiness: this replica can serve traffic (DB + Redis reachable)."""
    checks = {"database": False, "redis": False}
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        checks["database"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        checks["redis"] = bool(REDIS.ping())
    except Exception:  # noqa: BLE001
        pass
    ready = all(checks.values())
    return Response(
        content=json.dumps({"ready": ready, "instance": _INSTANCE, "checks": checks}),
        media_type="application/json",
        status_code=200 if ready else 503,
    )

# --- Prometheus command-path metrics ---------------------------------------
COMMANDS_ISSUED = Counter(
    "diep_commands_issued_total", "Commands accepted and persisted as PENDING",
    ["device_type", "command_type"])
COMMANDS_SENT = Counter(
    "diep_commands_sent_total", "Commands successfully produced to Kafka",
    ["device_type", "command_type"])
COMMANDS_ACKED = Counter(
    "diep_commands_acked_total", "Device acks received (result = ACKED|FAILED)",
    ["device_type", "command_type", "result"])
COMMANDS_REJECTED = Counter(
    "diep_commands_rejected_total", "Commands not dispatched",
    ["reason"])  # unknown_device | invalid_command | kafka_error
DERMS_REQUESTS = Counter(
    "diep_derms_requests_total", "DERMS requests accepted",
    ["request_type"])
DERMS_COMMANDS = Counter(
    "diep_derms_commands_total", "DERMS commands produced",
    ["request_type", "command_type"])
ANALYTICS_QUERIES = Counter(
    "diep_analytics_queries_total", "Analytics queries served",
    ["query_type"])  # forecast | anomalies | predictive_maintenance | summary
DISPATCH_LATENCY = Histogram(
    "diep_command_dispatch_seconds",
    "POST /commands handler latency: validate + persist + Kafka produce")
ACK_LATENCY = Histogram(
    "diep_command_ack_latency_seconds",
    "Seconds from command creation to device ack", ["result"])

# Lazily-initialised Kafka producer. Created on first use rather than at import
# so the app still starts if Kafka is briefly unavailable at boot (FastAPI has
# no depends_on for Kafka).
_producer = None


def get_producer():
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            acks="all",
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            retries=3,
            **_kafka_security_kwargs(),
        )
    return _producer


# get_conn() is imported from common.py (see top-of-file import).


def _redis_status_key(command_id):
    return f"command:{command_id}"


def _mirror_status(command_id, status, device_id=None, command_type=None, error=None):
    """Mirror command status into Redis for fast live lookup (24h TTL)."""
    key = _redis_status_key(command_id)
    fields = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if device_id is not None:
        fields["device_id"] = device_id
    if command_type is not None:
        fields["command_type"] = command_type
    if error is not None:
        fields["error"] = error
    try:
        REDIS.hset(key, mapping=fields)
        REDIS.expire(key, 86400)
    except redis.RedisError:
        # Redis is a cache mirror, not the source of truth — never fail the
        # request because the mirror is unavailable.
        pass


def _state_key(device_id: str) -> str:
    return f"state:{device_id}"


def _decode_redis_value(value: str):
    if value is None:
        return None
    try:
        if value.startswith("{") or value.startswith("["):
            return json.loads(value)
    except Exception:
        pass
    for typ in (int, float):
        try:
            return typ(value)
        except Exception:
            continue
    return value


def _get_cached_state(device_id: str) -> dict:
    try:
        raw = REDIS.hgetall(_state_key(device_id))
    except redis.RedisError:
        return {}
    if not raw:
        return {}
    return {k: _decode_redis_value(v) for k, v in raw.items()}


def _persist_state(device_id: str, fields: dict) -> None:
    key = _state_key(device_id)
    payload = {}
    for name, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            payload[name] = json.dumps(value)
        else:
            payload[name] = str(value)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        REDIS.hset(key, mapping=payload)
        REDIS.expire(key, 86400)
    except redis.RedisError:
        pass


def _device_row(device_id: str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT d.device_id, d.device_type, d.location, d.status, d.site_name, s.site_type, s.latitude, s.longitude "
        "FROM devices d LEFT JOIN sites s USING (site_name) WHERE d.device_id = %s",
        (device_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _latest_telemetry_for(device_id: str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM telemetry WHERE device_id = %s ORDER BY time DESC LIMIT 1",
        (device_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _latest_command_for(device_id: str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT command_id, command_type, status, error_message, created_at, dispatched_at, acked_at "
        "FROM commands WHERE device_id = %s ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _build_asset_record(device):
    state = _get_cached_state(device["device_id"])
    return {
        "device_id": device["device_id"],
        "device_type": device["device_type"],
        "location": device["location"],
        "site_name": device.get("site_name"),
        "site_type": device.get("site_type"),
        "status": device["status"],
        "current_state": state,
        "asset_metadata": _load_asset_metadata(device["device_id"], device["device_type"]),
    }


def _load_asset_metadata(device_id: str, device_type: str) -> dict:
    mapping = {
        "battery": ("battery_assets", "asset_id"),
        "solar_inverter": ("solar_assets", "asset_id"),
        "ev_charger": ("ev_chargers", "charger_id"),
    }
    if device_type not in mapping:
        return {}
    table, key_col = mapping[device_type]
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        f"SELECT * FROM {table} WHERE {key_col} = %s",
        (device_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


def _evaluate_health(device, state: dict) -> dict:
    status = device.get("status", "UNKNOWN")
    if status.upper() != "ONLINE":
        return {"health": "OFFLINE", "reason": "Device registry reports offline or unavailable"}

    last_seen = state.get("last_seen")
    if last_seen:
        try:
            last_seen_dt = datetime.fromisoformat(last_seen)
            age_seconds = (datetime.now(timezone.utc) - last_seen_dt).total_seconds()
            if age_seconds > 300:
                return {
                    "health": "DEGRADED",
                    "reason": "No recent telemetry or command update in the last 5 minutes",
                    "last_seen_seconds": age_seconds,
                }
        except Exception:
            pass
    else:
        return {"health": "UNKNOWN", "reason": "No cached current state available"}

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT severity, message, raised_at FROM alarms WHERE device_id = %s ORDER BY raised_at DESC LIMIT 1",
        (device["device_id"],),
    )
    alarm = cur.fetchone()
    cur.close()
    conn.close()

    if alarm:
        severity = alarm.get("severity", "UNKNOWN").upper()
        return {
            "health": "DEGRADED" if severity != "OK" else "OK",
            "reason": alarm.get("message", "Recent alarm event detected"),
            "alarm_severity": severity,
            "alarm_raised_at": alarm.get("raised_at").isoformat() if alarm.get("raised_at") else None,
        }

    return {"health": "OK", "reason": "Device is online and state is current"}


def _state_from_db(device_id: str) -> dict | None:
    device = _device_row(device_id)
    if device is None:
        return None
    telemetry = _latest_telemetry_for(device_id)
    command = _latest_command_for(device_id)
    state = {
        "device_id": device_id,
        "device_type": device["device_type"],
        "status": device["status"],
        "site_name": device.get("site_name"),
        "location": device.get("location"),
        "last_telemetry": telemetry,
        "last_command": command,
    }
    return state


def _record_analytics_event(event_type: str, device_id: str | None, site_name: str | None, severity: str, details: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analytics_events (event_type, device_id, site_name, severity, details) VALUES (%s, %s, %s, %s, %s)",
        (event_type, device_id, site_name, severity, json.dumps(details)),
    )
    conn.commit()
    cur.close()
    conn.close()


def _telemetry_series(device_id: str, limit: int = 72):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT time, power_kw, solar_kw, battery_soc, voltage, current, frequency FROM telemetry "
        "WHERE device_id = %s ORDER BY time DESC LIMIT %s",
        (device_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return list(reversed(rows))


def _compute_trend(series: list[dict], key: str):
    points = [(i, row[key]) for i, row in enumerate(series) if row.get(key) is not None]
    if len(points) < 2:
        return None
    xs, ys = zip(*points)
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = numerator / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _forecast_series(device_id: str, horizon_hours: int = 24):
    series = _telemetry_series(device_id, limit=48)
    if not series:
        return []
    last_time = series[-1]["time"]
    forecast_points = []
    metrics = []
    for key in ("power_kw", "solar_kw", "battery_soc"):
        trend = _compute_trend(series, key)
        values = [row[key] for row in series if row.get(key) is not None]
        if not values:
            continue
        baseline = values[-1]
        slope = trend[0] if trend is not None else 0.0
        metrics.append((key, baseline, slope))
    for hour in range(1, horizon_hours + 1):
        sample_time = last_time + timedelta(hours=hour)
        point = {"time": sample_time.isoformat()}
        for key, baseline, slope in metrics:
            point[key] = max(0.0, baseline + slope * hour)
        forecast_points.append(point)
    return forecast_points


def _detect_anomalies(device_id: str, window: int = 24):
    series = _telemetry_series(device_id, limit=window * 6)
    if not series:
        return []
    power_values = [row["power_kw"] for row in series if row.get("power_kw") is not None]
    if len(power_values) < 2:
        return []
    mean = statistics.mean(power_values)
    stdev = statistics.stdev(power_values)
    anomalies = []
    for row in series:
        power = row.get("power_kw")
        if power is not None and stdev > 0 and abs(power - mean) > 2 * stdev:
            anomalies.append({
                "time": row["time"].isoformat(),
                "metric": "power_kw",
                "value": power,
                "threshold_high": mean + 2 * stdev,
                "threshold_low": mean - 2 * stdev,
                "reason": "Deviation exceeds 2 sigma",
            })
        frequency = row.get("frequency")
        if frequency is not None and not (49.0 <= frequency <= 51.0):
            anomalies.append({
                "time": row["time"].isoformat(),
                "metric": "frequency",
                "value": frequency,
                "reason": "Frequency out of nominal range",
            })
    return anomalies


def _predictive_maintenance_insight(device_id: str):
    device = _device_row(device_id)
    if device is None:
        return None
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT COUNT(*) AS failures FROM commands WHERE device_id = %s AND status = 'FAILED' AND created_at > now() - interval '7 days'",
        (device_id,),
    )
    failures = cur.fetchone()["failures"]
    cur.execute(
        "SELECT COUNT(*) AS alarms FROM alarms WHERE device_id = %s AND raised_at > now() - interval '14 days'",
        (device_id,),
    )
    alarms = cur.fetchone()["alarms"]
    cur.close()
    conn.close()

    state = _get_cached_state(device_id) or _state_from_db(device_id) or {}
    soc = state.get("battery_soc")
    severity = "OK"
    reasons = []
    score = 0
    if failures > 0:
        score += failures * 2
        reasons.append(f"{failures} failed command(s) in last 7 days")
    if alarms > 0:
        score += alarms * 2
        reasons.append(f"{alarms} alarm(s) in last 14 days")
    if soc is not None and soc < 30 and device["device_type"] == "battery":
        score += 2
        reasons.append("Low battery state of charge")
    if score >= 6:
        severity = "HIGH"
    elif score >= 3:
        severity = "MEDIUM"
    elif score > 0:
        severity = "LOW"

    insight = {
        "device_id": device_id,
        "device_type": device["device_type"],
        "status": device["status"],
        "severity": severity,
        "score": score,
        "reasons": reasons,
    }
    _record_analytics_event("predictive_maintenance", device_id, device.get("site_name"), severity, insight)
    return insight


def _analytics_summary(site_name: str | None = None):
    filter_clause = ""
    params = []
    if site_name:
        filter_clause = "WHERE site_name = %s"
        params.append(site_name)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        f"SELECT device_type, status, COUNT(*) AS count FROM devices {filter_clause} GROUP BY device_type, status",
        tuple(params),
    )
    groups = cur.fetchall()
    cur.execute(
        f"SELECT COUNT(*) AS event_count FROM analytics_events {filter_clause}",
        tuple(params),
    )
    events = cur.fetchone()["event_count"]
    cur.close()
    conn.close()
    return {
        "device_summary": [{"device_type": row["device_type"], "status": row["status"], "count": row["count"]} for row in groups],
        "analytics_event_count": events,
        "site_name": site_name,
    }


def _forecast_target(site_name: str | None = None):
    if site_name:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT device_id, device_type FROM devices WHERE site_name = %s ORDER BY created_at DESC LIMIT 1",
            (site_name,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    return None


def _select_forecast_device(device_id: str | None, site_name: str | None):
    if device_id:
        device = _device_row(device_id)
        if device is None:
            raise HTTPException(status_code=404, detail=f"Unknown device_id '{device_id}'")
        return device
    if site_name:
        return _forecast_target(site_name)
    raise HTTPException(status_code=422, detail="device_id or site_name is required for analytics")


def _insert_derms_request(request_type: str, params: dict,
                          site_name: str | None = None,
                          device_id: str | None = None) -> str:
    """Persist a DERMS request and return its generated request_id."""
    request_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO derms_requests (request_id, request_type, site_name, device_id, params) "
        "VALUES (%s, %s, %s, %s, %s)",
        (request_id, request_type, site_name, device_id, json.dumps(params)),
    )
    conn.commit()
    cur.close()
    conn.close()
    return request_id


def _update_derms_request_status(request_id: str, status: str, executed_at=None, completed_at=None, error_message=None):
    conn = get_conn()
    cur = conn.cursor()
    fields = [status]
    updates = ["status = %s"]
    if executed_at is not None:
        updates.append("executed_at = %s")
        fields.append(executed_at)
    if completed_at is not None:
        updates.append("completed_at = %s")
        fields.append(completed_at)
    if error_message is not None:
        updates.append("error_message = %s")
        fields.append(error_message)
    fields.append(request_id)
    cur.execute(
        f"UPDATE derms_requests SET {', '.join(updates)} WHERE request_id = %s",
        tuple(fields),
    )
    conn.commit()
    cur.close()
    conn.close()


def _select_device(device_type: str, site_name: str | None = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = (
        "SELECT device_id, device_type, location, status, site_name FROM devices "
        "WHERE device_type = %s AND status = 'ONLINE'"
    )
    params = [device_type]
    if site_name:
        query += " AND site_name = %s"
        params.append(site_name)
    query += " ORDER BY created_at DESC LIMIT 1"
    cur.execute(query, tuple(params))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _execute_derms_command(request_type: str, request_id: str, device_id: str, command_type: str, params: dict):
    try:
        # Internal trusted call — the /derms HTTP route already enforced auth.
        result = _dispatch_command(CommandRequest(
            device_id=device_id,
            command_type=command_type,
            params=params,
            issued_by="derms",
        ))
        DERMS_COMMANDS.labels(request_type, command_type).inc()
        _update_derms_request_status(
            request_id,
            "EXECUTED",
            executed_at=datetime.now(timezone.utc),
        )
        return {
            "request_id": request_id,
            "device_id": device_id,
            "command_type": command_type,
            "command": result,
        }
    except HTTPException as exc:
        _update_derms_request_status(
            request_id,
            "FAILED",
            executed_at=datetime.now(timezone.utc),
            error_message=str(exc.detail),
        )
        raise


class CommandRequest(BaseModel):
    device_id: str = Field(..., examples=["EV001"])
    command_type: str = Field(..., examples=["start_charging"])
    params: dict = Field(default_factory=dict)
    issued_by: str = Field(default="api")


class AckRequest(BaseModel):
    status: str = Field(..., examples=["ACKED"])  # ACKED | FAILED
    error: str | None = None


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., examples=["METER001"])
    time: datetime | None = Field(default=None, examples=["2026-06-02T12:00:00Z"])
    voltage: float
    current: float
    power_kw: float
    frequency: float
    solar_kw: float
    battery_soc: float
    grid_import_kw: float
    grid_export_kw: float
    # Phase 9-Schema: optional device-class extended fields (nullable columns).
    power_factor: float | None = None
    energy_import_kwh: float | None = None
    energy_export_kwh: float | None = None
    temperature: float | None = None
    soh: float | None = None
    state: str | None = None
    # Per-reading device-specific long tail (vehicle_soc, connector_status,
    # session_energy_kwh, load_kw, setpoint_kw, grid_connected, mode, ...).
    extra: dict = Field(default_factory=dict)


class AssetRegistration(BaseModel):
    device_id: str = Field(..., examples=["BAT002"])
    device_type: str = Field(..., examples=["battery"])
    location: str = Field(..., examples=["Abuja Site B"])
    site_name: str | None = Field(None, examples=["Abuja Site A"])
    status: str = Field(default="UNKNOWN", examples=["ONLINE"])
    tenant_id: str | None = Field(None, examples=["acme"])  # Phase 12; defaults to 'default'
    metadata: dict = Field(default_factory=dict)


def _assert_tenant_access(principal, device_id: str) -> None:
    """Phase 12 — a tenant-scoped principal may only touch its own tenant's devices.
    Global principals (admin/service, tenant=None) are unrestricted."""
    if principal is None or principal.tenant is None:
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT tenant_id FROM devices WHERE device_id = %s", (device_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is not None and row[0] != principal.tenant:
        raise HTTPException(status_code=403,
                            detail=f"device '{device_id}' belongs to another tenant")


@app.post("/assets", status_code=201)
def register_asset(asset: AssetRegistration,
                   principal=Depends(require_role("admin", "engineer"))):
    # Phase 12: device tenant = explicit (global admin) or the caller's tenant, else 'default'.
    device_tenant = asset.tenant_id or principal.tenant or "default"
    auth.audit(principal, "register_asset", asset.device_id, "ok", site=asset.site_name,
               detail={"device_type": asset.device_type, "site_name": asset.site_name,
                "tenant": device_tenant})
    conn = get_conn()
    cur = conn.cursor()
    if asset.site_name:
        cur.execute(
            "INSERT INTO sites (site_name, site_type) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (asset.site_name, "unknown"),
        )
    try:
        cur.execute(
            "INSERT INTO devices (device_id, device_type, location, status, site_name, tenant_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (asset.device_id, asset.device_type, asset.location, asset.status,
             asset.site_name, device_tenant),
        )
        conn.commit()
    except psycopg2.IntegrityError as exc:
        conn.rollback()
        cur.close()
        conn.close()
        raise HTTPException(status_code=409, detail=str(exc))
    cur.close()
    conn.close()
    return get_asset(asset.device_id)


@app.get("/assets")
def list_assets(principal=Depends(require_role("viewer", "operator", "admin", "service"))):
    """List assets, scoped to the caller's tenant (Phase 12). Global principals see all."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if principal.tenant is None:
        cur.execute(
            "SELECT d.device_id, d.device_type, d.location, d.status, d.site_name, s.site_type "
            "FROM devices d LEFT JOIN sites s USING (site_name) ORDER BY d.device_id"
        )
    else:
        cur.execute(
            "SELECT d.device_id, d.device_type, d.location, d.status, d.site_name, s.site_type "
            "FROM devices d LEFT JOIN sites s USING (site_name) "
            "WHERE d.tenant_id = %s ORDER BY d.device_id",
            (principal.tenant,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"assets": [_build_asset_record(row) for row in rows]}


@app.get("/assets/{device_id}")
def get_asset(device_id: str):
    row = _device_row(device_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset '{device_id}'")
    return _build_asset_record(row)


@app.get("/state/{device_id}")
def get_device_state(device_id: str):
    state = _get_cached_state(device_id)
    if state:
        return state
    state = _state_from_db(device_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown device_id '{device_id}'")
    return state


@app.get("/assets/{device_id}/health")
def get_asset_health(device_id: str):
    device = _device_row(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset '{device_id}'")
    state = _get_cached_state(device_id)
    return _evaluate_health(device, state)


@app.get("/health/assets")
def assets_health():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT device_id, device_type, status FROM devices ORDER BY device_id"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {
        "assets": [
            {"device_id": row["device_id"], "health": _evaluate_health(row, _get_cached_state(row["device_id"]))}
            for row in rows
        ]
    }


# ---------------------------------------------------------------------------
# Phase 9H/9I — Device onboarding workflow + certification harness.
# State machine: REGISTERED -> VALIDATED -> CERTIFIED -> PRODUCTION_READY.
# Backed by device_onboarding + device_certifications (sql/007_onboarding.sql).
# ---------------------------------------------------------------------------

ONBOARDING_STATES = ["REGISTERED", "VALIDATED", "CERTIFIED", "PRODUCTION_READY"]

# The six certification tests required by Phase 9I.
CERTIFICATION_TESTS = ["connectivity", "telemetry", "command", "ack", "failover", "security"]

# Telemetry is considered "live" for onboarding purposes if seen within this window.
ONBOARDING_TELEMETRY_FRESH_SECONDS = 300


def _onboarding_row(device_id: str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, device_id, site_name, protocol, vendor, status, validation, notes, "
        "registered_at, validated_at, certified_at, production_approved_at "
        "FROM device_onboarding WHERE device_id = %s",
        (device_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _onboarding_record(row):
    """Serialize an onboarding row plus its latest certification results."""
    record = dict(row)
    for ts in ("registered_at", "validated_at", "certified_at", "production_approved_at"):
        if record.get(ts) is not None:
            record[ts] = record[ts].isoformat()
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Latest result per test for this device.
    cur.execute(
        "SELECT DISTINCT ON (test_name) test_name, result, details, run_at "
        "FROM device_certifications WHERE device_id = %s "
        "ORDER BY test_name, run_at DESC",
        (record["device_id"],),
    )
    certs = cur.fetchall()
    cur.close()
    conn.close()
    record["certifications"] = [
        {
            "test_name": c["test_name"],
            "result": c["result"],
            "details": c["details"],
            "run_at": c["run_at"].isoformat() if c["run_at"] else None,
        }
        for c in certs
    ]
    return record


class OnboardingEnrollment(BaseModel):
    device_id: str = Field(..., examples=["BAT002"])
    site_name: str | None = Field(None, examples=["Abuja Site A"])
    protocol: str | None = Field(None, examples=["sunspec", "modbus", "dlms", "ocpp"])
    vendor: str | None = Field(None, examples=["Huawei"])
    notes: str | None = None


@app.post("/onboarding", status_code=201)
def enroll_device(enrollment: OnboardingEnrollment,
                  principal=Depends(require_role("admin", "engineer"))):
    auth.audit(principal, "onboarding_enroll", enrollment.device_id, "ok", site=enrollment.site_name,
               detail={"protocol": enrollment.protocol, "vendor": enrollment.vendor})
    """Enroll an already-registered device into the onboarding pipeline (REGISTERED)."""
    if _device_row(enrollment.device_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown device '{enrollment.device_id}' — register it via POST /assets first",
        )
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO device_onboarding (device_id, site_name, protocol, vendor, notes, status) "
            "VALUES (%s, %s, %s, %s, %s, 'REGISTERED')",
            (enrollment.device_id, enrollment.site_name, enrollment.protocol, enrollment.vendor, enrollment.notes),
        )
        conn.commit()
    except psycopg2.IntegrityError as exc:
        conn.rollback()
        cur.close()
        conn.close()
        raise HTTPException(status_code=409, detail=f"Device '{enrollment.device_id}' is already enrolled")
    cur.close()
    conn.close()
    return _onboarding_record(_onboarding_row(enrollment.device_id))


@app.get("/onboarding")
def list_onboarding(status: str | None = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if status:
        cur.execute(
            "SELECT device_id, site_name, protocol, vendor, status, registered_at "
            "FROM device_onboarding WHERE status = %s ORDER BY registered_at DESC",
            (status.upper(),),
        )
    else:
        cur.execute(
            "SELECT device_id, site_name, protocol, vendor, status, registered_at "
            "FROM device_onboarding ORDER BY registered_at DESC"
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {
        "onboarding": [
            {**dict(r), "registered_at": r["registered_at"].isoformat() if r["registered_at"] else None}
            for r in rows
        ]
    }


@app.get("/onboarding/{device_id}")
def get_onboarding(device_id: str):
    row = _onboarding_row(device_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' is not enrolled in onboarding")
    return _onboarding_record(row)


def _advance_onboarding(device_id: str, new_status: str, timestamp_col: str, validation: dict | None = None):
    conn = get_conn()
    cur = conn.cursor()
    if validation is not None:
        cur.execute(
            f"UPDATE device_onboarding SET status = %s, {timestamp_col} = now(), validation = %s "
            "WHERE device_id = %s",
            (new_status, json.dumps(validation), device_id),
        )
    else:
        cur.execute(
            f"UPDATE device_onboarding SET status = %s, {timestamp_col} = now() WHERE device_id = %s",
            (new_status, device_id),
        )
    conn.commit()
    cur.close()
    conn.close()


@app.post("/onboarding/{device_id}/validate")
def validate_onboarding(device_id: str,
                        principal=Depends(require_role("admin", "engineer"))):
    auth.audit(principal, "onboarding_validate", device_id, "ok", device_id=device_id)
    """Run pre-certification validation checks and advance REGISTERED -> VALIDATED."""
    row = _onboarding_row(device_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' is not enrolled in onboarding")
    if row["status"] not in ("REGISTERED", "VALIDATED"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot validate from status '{row['status']}' (expected REGISTERED)",
        )

    checks = {
        "device_registered": _device_row(device_id) is not None,
        "protocol_declared": bool(row["protocol"]),
        "site_assigned": bool(row["site_name"]),
        "telemetry_seen": _latest_telemetry_for(device_id) is not None,
    }
    # Protocol and live telemetry are the hard gates; site is advisory.
    passed = checks["device_registered"] and checks["protocol_declared"] and checks["telemetry_seen"]
    validation = {"checks": checks, "passed": passed}

    if passed:
        _advance_onboarding(device_id, "VALIDATED", "validated_at", validation)
    else:
        # Record the failed validation without advancing.
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE device_onboarding SET validation = %s WHERE device_id = %s",
            (json.dumps(validation), device_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    return _onboarding_record(_onboarding_row(device_id))


def _run_certification_tests(device_id: str) -> list[dict]:
    """Execute the six Phase 9I certification tests against current platform state.

    Tests reflect real observable state rather than synthetic actuation, so they are
    safe to run against live or simulated devices. failover/security are honestly
    reported as SKIPPED pending Phase 9K/9J rather than falsely passed.
    """
    now = datetime.now(timezone.utc)
    results: list[dict] = []

    # 1. connectivity — device is known and not marked OFFLINE.
    device = _device_row(device_id)
    connected = device is not None and (device["status"] or "").upper() not in ("OFFLINE", "UNKNOWN")
    results.append({
        "test_name": "connectivity",
        "result": "PASS" if connected else "FAIL",
        "details": {"status": device["status"] if device else None},
    })

    # 2. telemetry — fresh telemetry within the freshness window.
    latest = _latest_telemetry_for(device_id)
    fresh = False
    age_seconds = None
    if latest and latest.get("time"):
        ts = latest["time"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_seconds = (now - ts).total_seconds()
        fresh = age_seconds <= ONBOARDING_TELEMETRY_FRESH_SECONDS
    results.append({
        "test_name": "telemetry",
        "result": "PASS" if fresh else "FAIL",
        "details": {"age_seconds": age_seconds, "window_seconds": ONBOARDING_TELEMETRY_FRESH_SECONDS},
    })

    # 3/4. command + ack — exercise the command path via its history.
    last_cmd = _latest_command_for(device_id)
    if last_cmd is None:
        results.append({"test_name": "command", "result": "PENDING",
                        "details": {"reason": "no command issued yet"}})
        results.append({"test_name": "ack", "result": "PENDING",
                        "details": {"reason": "no command issued yet"}})
    else:
        dispatched = last_cmd.get("dispatched_at") is not None
        acked = (last_cmd.get("status") or "").upper() in ("ACKED", "COMPLETED")
        results.append({
            "test_name": "command",
            "result": "PASS" if dispatched else "FAIL",
            "details": {"command_id": last_cmd.get("command_id"), "status": last_cmd.get("status")},
        })
        results.append({
            "test_name": "ack",
            "result": "PASS" if acked else "FAIL",
            "details": {"command_id": last_cmd.get("command_id"), "status": last_cmd.get("status")},
        })

    # 5. failover (Phase 9I-full, real) — resilience: telemetry continuity through
    #    reconnects + a live datastore replica (HA, from 9K).
    fo = {}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM telemetry WHERE device_id = %s AND time > now() - interval '3 minutes'",
        (device_id,),
    )
    fo["telemetry_samples_3m"] = cur.fetchone()[0]
    cur.close()
    conn.close()
    fo["continuous"] = fo["telemetry_samples_3m"] >= 10   # ~5s cadence → resilient if steady
    try:
        fo["redis_connected_replicas"] = int(REDIS.info("replication").get("connected_slaves", 0))
    except Exception:  # noqa: BLE001
        fo["redis_connected_replicas"] = 0
    fo["redundancy"] = fo["redis_connected_replicas"] >= 1
    failover_pass = fo["continuous"] and fo["redundancy"]
    results.append({
        "test_name": "failover",
        "result": "PASS" if failover_pass else "FAIL",
        "details": fo,
    })

    # 6. security (Phase 9I-full, real) — API auth enforced + plaintext MQTT retired
    #    (the harness probes diep-mqtt:1883; refused == mTLS-only, from 9J-S4).
    sec = {"api_auth_enforced": bool(auth.AUTH_ENFORCED)}

    def _tcp_open(host, port, timeout=2.0):
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except OSError:
            return False

    sec["mqtt_plaintext_1883_open"] = _tcp_open(os.getenv("MQTT_BROKER", "diep-mqtt"), 1883)
    sec["mqtt_mtls_only"] = not sec["mqtt_plaintext_1883_open"]
    security_pass = sec["api_auth_enforced"] and sec["mqtt_mtls_only"]
    results.append({
        "test_name": "security",
        "result": "PASS" if security_pass else "FAIL",
        "details": sec,
    })

    # Persist this certification run.
    conn = get_conn()
    cur = conn.cursor()
    for r in results:
        cur.execute(
            "INSERT INTO device_certifications (device_id, test_name, result, details) "
            "VALUES (%s, %s, %s, %s)",
            (device_id, r["test_name"], r["result"], json.dumps(r["details"])),
        )
    conn.commit()
    cur.close()
    conn.close()
    return results


@app.post("/onboarding/{device_id}/certify")
def certify_onboarding(device_id: str,
                       principal=Depends(require_role("admin"))):
    auth.audit(principal, "onboarding_certify", device_id, "ok", device_id=device_id)
    """Run the six-test certification harness and advance VALIDATED -> CERTIFIED."""
    row = _onboarding_row(device_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' is not enrolled in onboarding")
    # VALIDATED→CERTIFIED is the normal path; CERTIFIED/PRODUCTION_READY allow
    # periodic RE-certification (Phase 9I) without downgrading a production device.
    if row["status"] not in ("VALIDATED", "CERTIFIED", "PRODUCTION_READY"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot certify from status '{row['status']}' (run /validate first)",
        )

    results = _run_certification_tests(device_id)
    failed = [r["test_name"] for r in results if r["result"] == "FAIL"]
    pending = [r["test_name"] for r in results if r["result"] == "PENDING"]
    certified = not failed and not pending

    # Advance to CERTIFIED only from VALIDATED; never downgrade an already-approved device.
    if certified and row["status"] == "VALIDATED":
        _advance_onboarding(device_id, "CERTIFIED", "certified_at")

    return {
        "device_id": device_id,
        "certified": certified,
        "failed_tests": failed,
        "pending_tests": pending,
        "results": results,
        "onboarding": _onboarding_record(_onboarding_row(device_id)),
    }


class ApprovalRequest(BaseModel):
    approved_by: str = Field(default="operator", examples=["jane.operator"])
    notes: str | None = None


@app.post("/onboarding/{device_id}/approve")
def approve_onboarding(device_id: str, approval: ApprovalRequest,
                       principal=Depends(require_role("admin"))):
    auth.audit(principal, "onboarding_approve", device_id, "ok", device_id=device_id,
               detail={"approved_by": approval.approved_by})
    """Final human gate: advance CERTIFIED -> PRODUCTION_READY."""
    row = _onboarding_row(device_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' is not enrolled in onboarding")
    if row["status"] != "CERTIFIED":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve from status '{row['status']}' (must be CERTIFIED)",
        )
    note = f"approved by {approval.approved_by}"
    if approval.notes:
        note += f": {approval.notes}"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE device_onboarding SET status = 'PRODUCTION_READY', production_approved_at = now(), "
        "notes = %s WHERE device_id = %s",
        (note, device_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return _onboarding_record(_onboarding_row(device_id))


@app.get("/fleet/overview")
def fleet_overview():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT device_type, status, COUNT(*) AS count FROM devices GROUP BY device_type, status"
    )
    rows = cur.fetchall()
    cur.execute(
        "SELECT site_name, COUNT(*) AS count FROM devices GROUP BY site_name"
    )
    sites = cur.fetchall()
    cur.close()
    conn.close()
    counts = {}
    for device_type, status, count in rows:
        counts.setdefault(device_type, {})[status] = count
    return {
        "total_assets": sum(count for _, _, count in rows),
        "by_device_type": counts,
        "by_site": {site_name: count for site_name, count in sites if site_name},
    }


@app.get("/sites/overview")
def sites_overview():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT site_name, site_type, latitude, longitude FROM sites ORDER BY site_name"
    )
    site_rows = cur.fetchall()
    out = []
    for site in site_rows:
        cur.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status = 'ONLINE' THEN 1 ELSE 0 END) AS online "
            "FROM devices WHERE site_name = %s",
            (site["site_name"],),
        )
        counts = cur.fetchone()
        cur.execute(
            "SELECT MAX(time) AS latest_telemetry FROM telemetry "
            "WHERE device_id IN (SELECT device_id FROM devices WHERE site_name = %s)",
            (site["site_name"],),
        )
        telemetry = cur.fetchone()
        out.append(
            {
                "site_name": site["site_name"],
                "site_type": site["site_type"],
                "latitude": site["latitude"],
                "longitude": site["longitude"],
                "asset_count": counts["total"],
                "online_assets": counts["online"],
                "latest_telemetry": telemetry["latest_telemetry"].isoformat() if telemetry["latest_telemetry"] else None,
            }
        )
    cur.close()
    conn.close()
    return {"sites": out}


@app.get("/sites/{site_name}/overview")
def site_overview(site_name: str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT site_name, site_type, latitude, longitude FROM sites WHERE site_name = %s",
        (site_name,),
    )
    site = cur.fetchone()
    if site is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail=f"Unknown site '{site_name}'")
    cur.execute(
        "SELECT device_id, device_type, status FROM devices WHERE site_name = %s ORDER BY device_id",
        (site_name,),
    )
    assets = cur.fetchall()
    cur.execute(
        "SELECT MAX(time) AS latest_telemetry FROM telemetry "
        "WHERE device_id IN (SELECT device_id FROM devices WHERE site_name = %s)",
        (site_name,),
    )
    telemetry = cur.fetchone()
    cur.close()
    conn.close()
    return {
        "site_name": site["site_name"],
        "site_type": site["site_type"],
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "assets": [dict(asset) for asset in assets],
        "latest_telemetry": telemetry["latest_telemetry"].isoformat() if telemetry["latest_telemetry"] else None,
    }


class BatteryDispatchRequest(BaseModel):
    device_id: str | None = Field(None, examples=["BAT001"])
    site_name: str | None = Field(None, examples=["Abuja Site A"])
    target_soc: float = Field(..., ge=0, le=100, examples=[80])
    max_power_kw: float | None = Field(None, examples=[10])


class PeakShavingRequest(BaseModel):
    site_name: str | None = Field(None, examples=["Abuja Site A"])
    reduction_kw: float = Field(..., ge=0, examples=[5])
    max_power_kw: float | None = Field(None, examples=[10])


class DemandResponseRequest(BaseModel):
    site_name: str | None = Field(None, examples=["Abuja Site A"])
    event_duration_minutes: int = Field(..., ge=5, examples=[30])
    target_reduction_kw: float = Field(..., ge=0, examples=[5])


class LoadOptimizationRequest(BaseModel):
    site_name: str | None = Field(None, examples=["Abuja Site A"])
    objective: str = Field(default="maximize_solar", examples=["maximize_solar"])
    optimization_horizon_hours: int = Field(default=1, ge=1, examples=[2])


@app.post("/derms/battery_dispatch", status_code=202)
def battery_dispatch(request: BatteryDispatchRequest,
                     principal=Depends(require_role("operator")),
                     _rl=Depends(rate_limit("derms", 60, 60))):
    DERMS_REQUESTS.labels("battery_dispatch").inc()
    auth.audit(principal, "derms_battery_dispatch", request.device_id or request.site_name or "auto",
               "ok", site=request.site_name, device_id=request.device_id,
               detail={"target_soc": request.target_soc, "max_power_kw": request.max_power_kw})
    device = None
    if request.device_id:
        device = _device_row(request.device_id)
        if device is None:
            raise HTTPException(status_code=404, detail=f"Unknown device_id '{request.device_id}'")
        if device["device_type"] != "battery":
            raise HTTPException(status_code=422, detail="device_id must be a battery asset")
    else:
        device = _select_device("battery", request.site_name)
        if device is None:
            raise HTTPException(status_code=404, detail="No online battery found for the requested site")

    state = _get_cached_state(device["device_id"]) or _state_from_db(device["device_id"]) or {}
    current_soc = state.get("battery_soc")
    if current_soc is None:
        current_soc = 50.0

    if current_soc < request.target_soc:
        command_type = "charge"
    elif current_soc > request.target_soc:
        command_type = "discharge"
    else:
        command_type = "idle"

    params = {"target_soc": request.target_soc}
    if request.max_power_kw is not None:
        params["max_power_kw"] = request.max_power_kw

    request_id = _insert_derms_request(
        "battery_dispatch",
        {"target_soc": request.target_soc, "max_power_kw": request.max_power_kw},
        device["site_name"],
        device["device_id"],
    )
    return _execute_derms_command("battery_dispatch", request_id, device["device_id"], command_type, params)


@app.post("/derms/peak_shaving", status_code=202)
def peak_shaving(request: PeakShavingRequest,
                 principal=Depends(require_role("operator")),
                 _rl=Depends(rate_limit("derms", 60, 60))):
    DERMS_REQUESTS.labels("peak_shaving").inc()
    auth.audit(principal, "derms_peak_shaving", request.site_name or "auto", "ok",
               site=request.site_name, detail={"reduction_kw": request.reduction_kw})
    device = _select_device("battery", request.site_name)
    if device is None:
        raise HTTPException(status_code=404, detail="No online battery available to support peak shaving")

    state = _get_cached_state(device["device_id"]) or _state_from_db(device["device_id"]) or {}
    current_soc = state.get("battery_soc")
    if current_soc is None:
        current_soc = 50.0
    if current_soc < 25:
        raise HTTPException(status_code=409, detail="Battery state of charge too low for safe peak shaving")

    max_power = request.max_power_kw or request.reduction_kw or 5.0
    params = {
        "max_power_kw": min(max_power, request.reduction_kw if request.reduction_kw > 0 else max_power),
        "target_soc": max(current_soc - 10, 20),
    }

    request_id = _insert_derms_request(
        "peak_shaving",
        {"reduction_kw": request.reduction_kw, "max_power_kw": request.max_power_kw},
        device["site_name"],
        device["device_id"],
    )
    return _execute_derms_command("peak_shaving", request_id, device["device_id"], "discharge", params)


@app.post("/derms/demand_response", status_code=202)
def demand_response(request: DemandResponseRequest,
                    principal=Depends(require_role("operator")),
                    _rl=Depends(rate_limit("derms", 60, 60))):
    DERMS_REQUESTS.labels("demand_response").inc()
    auth.audit(principal, "derms_demand_response", request.site_name or "auto", "ok",
               site=request.site_name, detail={"target_reduction_kw": request.target_reduction_kw})
    battery = _select_device("battery", request.site_name)
    if battery is not None:
        state = _get_cached_state(battery["device_id"]) or _state_from_db(battery["device_id"]) or {}
        current_soc = state.get("battery_soc") or 50.0
        if current_soc < 25:
            raise HTTPException(status_code=409, detail="Battery SOC too low for demand response discharge")
        params = {
            "max_power_kw": request.target_reduction_kw,
            "event_duration_minutes": request.event_duration_minutes,
        }
        request_id = _insert_derms_request(
            "demand_response",
            {"target_reduction_kw": request.target_reduction_kw, "event_duration_minutes": request.event_duration_minutes},
            battery["site_name"],
            battery["device_id"],
        )
        return _execute_derms_command("demand_response", request_id, battery["device_id"], "discharge", params)

    charger = _select_device("ev_charger", request.site_name)
    if charger is not None:
        request_id = _insert_derms_request(
            "demand_response",
            {"target_reduction_kw": request.target_reduction_kw, "event_duration_minutes": request.event_duration_minutes},
            charger["site_name"],
            charger["device_id"],
        )
        params = {"duration_minutes": request.event_duration_minutes}
        return _execute_derms_command("demand_response", request_id, charger["device_id"], "stop_charging", params)

    raise HTTPException(status_code=404, detail="No DERMS-capable asset available for demand response")


@app.post("/derms/load_optimization", status_code=202)
def load_optimization(request: LoadOptimizationRequest,
                      principal=Depends(require_role("operator")),
                      _rl=Depends(rate_limit("derms", 60, 60))):
    DERMS_REQUESTS.labels("load_optimization").inc()
    auth.audit(principal, "derms_load_optimization", request.site_name or "auto", "ok",
               site=request.site_name, detail={"objective": request.objective})
    battery = _select_device("battery", request.site_name)
    if battery is None:
        raise HTTPException(status_code=404, detail="No battery asset available for load optimization")

    state = _get_cached_state(battery["device_id"]) or _state_from_db(battery["device_id"]) or {}
    current_soc = state.get("battery_soc") or 50.0
    objective = request.objective.lower()
    if objective == "maximize_solar":
        command_type = "charge"
        target_soc = min(current_soc + 20, 90)
    elif objective == "min_cost":
        command_type = "charge" if current_soc < 50 else "discharge"
        target_soc = 50 if current_soc < 50 else max(current_soc - 20, 20)
    else:
        command_type = "charge" if current_soc < 60 else "discharge"
        target_soc = 60 if current_soc < 60 else max(current_soc - 20, 20)

    params = {
        "target_soc": target_soc,
        "max_power_kw": 10,
        "optimization_horizon_hours": request.optimization_horizon_hours,
    }
    request_id = _insert_derms_request(
        "load_optimization",
        {"objective": request.objective, "optimization_horizon_hours": request.optimization_horizon_hours},
        battery["site_name"],
        battery["device_id"],
    )
    return _execute_derms_command("load_optimization", request_id, battery["device_id"], command_type, params)


@app.get("/derms/requests")
def list_derms_requests(limit: int = 50, request_type: str | None = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if request_type:
        cur.execute(
            "SELECT request_id, request_type, site_name, device_id, params, status, created_at, executed_at, completed_at, error_message "
            "FROM derms_requests WHERE request_type = %s ORDER BY created_at DESC LIMIT %s",
            (request_type, limit),
        )
    else:
        cur.execute(
            "SELECT request_id, request_type, site_name, device_id, params, status, created_at, executed_at, completed_at, error_message "
            "FROM derms_requests ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for row in rows:
        record = dict(row)
        for ts in ("created_at", "executed_at", "completed_at"):
            if record.get(ts) is not None:
                record[ts] = record[ts].isoformat()
        out.append(record)
    return {"requests": out}


@app.get("/derms/requests/{request_id}")
def get_derms_request(request_id: str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT request_id, request_type, site_name, device_id, params, status, created_at, executed_at, completed_at, error_message "
        "FROM derms_requests WHERE request_id = %s",
        (request_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown DERMS request '{request_id}'")
    record = dict(row)
    for ts in ("created_at", "executed_at", "completed_at"):
        if record.get(ts) is not None:
            record[ts] = record[ts].isoformat()
    return record


@app.get("/analytics/forecast")
def analytics_forecast(device_id: str | None = None, site_name: str | None = None, horizon_hours: int = 24):
    ANALYTICS_QUERIES.labels("forecast").inc()
    target = _select_forecast_device(device_id, site_name)
    if target is None:
        raise HTTPException(status_code=404, detail="No forecast target found")
    forecast_points = _forecast_series(target["device_id"], horizon_hours)
    return {
        "device_id": target["device_id"],
        "device_type": target["device_type"],
        "horizon_hours": horizon_hours,
        "forecast": forecast_points,
    }


@app.get("/analytics/anomalies")
def analytics_anomalies(device_id: str | None = None, site_name: str | None = None, window_hours: int = 24):
    ANALYTICS_QUERIES.labels("anomalies").inc()
    if device_id is None and site_name is not None:
        target = _forecast_target(site_name)
        if target is None:
            raise HTTPException(status_code=404, detail="No device found for site")
        device_id = target["device_id"]
    if device_id is None:
        raise HTTPException(status_code=422, detail="device_id or site_name required for anomaly detection")
    anomalies = _detect_anomalies(device_id, window_hours)
    _record_analytics_event("anomaly_detection", device_id, site_name, "INFO", {"anomaly_count": len(anomalies)})
    return {
        "device_id": device_id,
        "window_hours": window_hours,
        "anomalies": anomalies,
    }


@app.get("/analytics/predictive_maintenance")
def analytics_predictive_maintenance(device_id: str | None = None, site_name: str | None = None):
    ANALYTICS_QUERIES.labels("predictive_maintenance").inc()
    if device_id is None:
        if site_name is None:
            raise HTTPException(status_code=422, detail="device_id or site_name required")
        target = _forecast_target(site_name)
        if target is None:
            raise HTTPException(status_code=404, detail="No device found for site")
        device_id = target["device_id"]
    insight = _predictive_maintenance_insight(device_id)
    if insight is None:
        raise HTTPException(status_code=404, detail=f"Unknown device_id '{device_id}'")
    return insight


@app.get("/analytics/summary")
def analytics_summary(site_name: str | None = None):
    ANALYTICS_QUERIES.labels("summary").inc()
    return _analytics_summary(site_name)


@app.get("/alarms")
def list_alarms(device_id: str | None = None, limit: int = 50):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if device_id:
        cur.execute(
            "SELECT id, device_id, alarm_type, severity, message, metadata, raised_at "
            "FROM alarms WHERE device_id = %s ORDER BY raised_at DESC LIMIT %s",
            (device_id, limit),
        )
    else:
        cur.execute(
            "SELECT id, device_id, alarm_type, severity, message, metadata, raised_at "
            "FROM alarms ORDER BY raised_at DESC LIMIT %s",
            (limit,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("raised_at") is not None:
            d["raised_at"] = d["raised_at"].isoformat()
        out.append(d)
    return {"alarms": out}


@app.get("/recommendations")
def recommendations(site_name: str | None = None, device_id: str | None = None):
    """Compose actionable operator recommendations by reusing the existing
    analytics helpers (predictive maintenance, anomaly detection) plus a low-SOC
    DERMS heuristic. No new analytics logic — this is an aggregation layer."""
    if device_id:
        device_ids = [device_id]
    else:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if site_name:
            cur.execute(
                "SELECT device_id FROM devices WHERE site_name = %s ORDER BY device_id",
                (site_name,),
            )
        else:
            cur.execute("SELECT device_id FROM devices ORDER BY device_id")
        device_ids = [r["device_id"] for r in cur.fetchall()]
        cur.close()
        conn.close()

    recs = []
    for did in device_ids:
        device = _device_row(did)
        if device is None:
            continue
        state = _get_cached_state(did) or _state_from_db(did) or {}

        # Low battery SOC -> suggest a DERMS battery dispatch (mirrors the
        # battery_dispatch heuristic in the DERMS endpoints).
        soc = state.get("battery_soc")
        if device["device_type"] == "battery" and soc is not None and soc < 30:
            recs.append({
                "device_id": did, "type": "soc_low", "severity": "MEDIUM",
                "message": f"{did} battery SOC low ({soc}%)",
                "suggested_action": "Dispatch battery to recharge",
                "suggested_endpoint": "POST /derms/battery_dispatch",
            })

        # Predictive maintenance risk (reuse helper).
        insight = _predictive_maintenance_insight(did)
        if insight and insight["severity"] in ("MEDIUM", "HIGH"):
            recs.append({
                "device_id": did, "type": "predictive_maintenance",
                "severity": insight["severity"],
                "message": f"Maintenance risk {insight['severity']}: "
                           f"{'; '.join(insight['reasons']) or 'elevated risk score'}",
                "suggested_action": "Inspect asset / review recent failures",
                "suggested_endpoint": f"GET /analytics/predictive_maintenance?device_id={did}",
            })

        # Telemetry anomalies (reuse helper).
        anomalies = _detect_anomalies(did)
        if anomalies:
            recs.append({
                "device_id": did, "type": "anomaly", "severity": "LOW",
                "message": f"{len(anomalies)} anomaly point(s) detected "
                           f"({anomalies[0]['metric']})",
                "suggested_action": "Review telemetry trend / acknowledge",
                "suggested_endpoint": f"GET /analytics/anomalies?device_id={did}",
            })
    return {"recommendations": recs}


@app.get("/reports/summary")
def reports_summary(site_name: str | None = None):
    """Aggregate operational report. Reuses _analytics_summary and adds command,
    DERMS, alarm, and telemetry-freshness rollups for the Reports page."""
    summary = _analytics_summary(site_name)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    site_filter = "WHERE d.site_name = %s" if site_name else ""
    params = (site_name,) if site_name else ()

    cur.execute(
        f"SELECT c.status, COUNT(*) AS count FROM commands c "
        f"JOIN devices d USING (device_id) {site_filter} GROUP BY c.status",
        params,
    )
    command_counts = {r["status"]: r["count"] for r in cur.fetchall()}

    if site_name:
        cur.execute(
            "SELECT status, COUNT(*) AS count FROM derms_requests WHERE site_name = %s GROUP BY status",
            (site_name,),
        )
    else:
        cur.execute("SELECT status, COUNT(*) AS count FROM derms_requests GROUP BY status")
    derms_counts = {r["status"]: r["count"] for r in cur.fetchall()}

    cur.execute(
        f"SELECT a.severity, COUNT(*) AS count FROM alarms a "
        f"JOIN devices d USING (device_id) {site_filter} GROUP BY a.severity",
        params,
    )
    alarm_counts = {r["severity"]: r["count"] for r in cur.fetchall()}

    cur.execute(
        f"SELECT d.device_id, MAX(t.time) AS latest FROM devices d "
        f"LEFT JOIN telemetry t USING (device_id) {site_filter} GROUP BY d.device_id",
        params,
    )
    latest_telemetry = {
        r["device_id"]: (r["latest"].isoformat() if r["latest"] else None)
        for r in cur.fetchall()
    }

    cur.close()
    conn.close()
    return {
        "site_name": site_name,
        "device_summary": summary["device_summary"],
        "analytics_event_count": summary["analytics_event_count"],
        "command_counts_by_status": command_counts,
        "derms_counts_by_status": derms_counts,
        "alarm_counts_by_severity": alarm_counts,
        "latest_telemetry": latest_telemetry,
        "note": "CSV export derived client-side from this JSON",
    }


@app.get("/")
def root():
    return {"platform": "DIEP", "status": "UP"}


@app.get("/health")
def health():
    return {"status": "UP", "platform": "DIEP"}


@app.get("/devices")
def get_devices():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, device_id, device_type, location, status FROM devices ORDER BY id"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"devices": [dict(r) for r in rows]}


@app.get("/telemetry/latest")
def latest_telemetry():
    """Latest telemetry row from TimescaleDB (was InfluxDB; retired in Phase 9-Data)."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM telemetry ORDER BY time DESC LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return {"message": "No telemetry found"}
    if row.get("time"):
        row["time"] = row["time"].isoformat()
    return row


@app.post("/telemetry", status_code=201)
def ingest_telemetry(payload: TelemetryPayload,
                     _p=Depends(require_role("service"))):
    insert_time = payload.time or datetime.now(timezone.utc)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT device_type, status, site_name, location FROM devices WHERE device_id = %s",
        (payload.device_id,),
    )
    device = cur.fetchone()
    if device is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail=f"Unknown device_id '{payload.device_id}'")

    try:
        cur.execute(
            """
            INSERT INTO telemetry (
                time, device_id, voltage, current, power_kw, frequency,
                solar_kw, battery_soc, grid_import_kw, grid_export_kw,
                power_factor, energy_import_kwh, energy_export_kwh,
                temperature, soh, state, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                insert_time,
                payload.device_id,
                payload.voltage,
                payload.current,
                payload.power_kw,
                payload.frequency,
                payload.solar_kw,
                payload.battery_soc,
                payload.grid_import_kw,
                payload.grid_export_kw,
                payload.power_factor,
                payload.energy_import_kwh,
                payload.energy_export_kwh,
                payload.temperature,
                payload.soh,
                payload.state,
                json.dumps(payload.extra or {}),
            ),
        )
        conn.commit()
        # Mirror to the twin (Redis). Phase 9-Schema: include extended fields +
        # the device-specific long tail so the digital twin shows them too.
        twin_state = {
            "device_type": device["device_type"],
            "site_name": device.get("site_name"),
            "location": device.get("location"),
            "status": device.get("status"),
            "last_seen": insert_time.isoformat(),
            "voltage": payload.voltage,
            "current": payload.current,
            "power_kw": payload.power_kw,
            "frequency": payload.frequency,
            "solar_kw": payload.solar_kw,
            "battery_soc": payload.battery_soc,
            "grid_import_kw": payload.grid_import_kw,
            "grid_export_kw": payload.grid_export_kw,
            "power_factor": payload.power_factor,
            "energy_import_kwh": payload.energy_import_kwh,
            "energy_export_kwh": payload.energy_export_kwh,
            "temperature": payload.temperature,
            "soh": payload.soh,
            "state": payload.state,
        }
        twin_state.update(payload.extra or {})
        _persist_state(payload.device_id, twin_state)
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        cur.close()
        conn.close()
    return {
        "status": "created",
        "device_id": payload.device_id,
        "time": insert_time.isoformat(),
    }


def _dispatch_command(cmd: CommandRequest):
    start = time.monotonic()
    # 1. Validate the target device exists in the registry.
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT device_type, status FROM devices WHERE device_id = %s", (cmd.device_id,)
    )
    row = cur.fetchone()
    if row is None:
        cur.close()
        conn.close()
        COMMANDS_REJECTED.labels("unknown_device").inc()
        raise HTTPException(status_code=404, detail=f"Unknown device_id '{cmd.device_id}'")
    device_type, device_status = row

    # 2. Validate the command is allowed for this device type (if we know the type).
    allowed = ALLOWED_COMMANDS.get(device_type)
    if allowed is not None and cmd.command_type not in allowed:
        cur.close()
        conn.close()
        COMMANDS_REJECTED.labels("invalid_command").inc()
        raise HTTPException(
            status_code=422,
            detail=f"command_type '{cmd.command_type}' not valid for device_type "
                   f"'{device_type}'. Allowed: {sorted(allowed)}",
        )

    # 3. Persist as PENDING (audit source of truth) before dispatch.
    command_id = str(uuid.uuid4())
    issued_at = datetime.now(timezone.utc)
    cur.execute(
        """
        INSERT INTO commands
            (command_id, device_id, device_type, command_type, params, status, issued_by, created_at)
        VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, %s)
        """,
        (command_id, cmd.device_id, device_type, cmd.command_type,
         json.dumps(cmd.params), cmd.issued_by, issued_at),
    )
    conn.commit()
    _mirror_status(command_id, "PENDING", cmd.device_id, cmd.command_type)
    COMMANDS_ISSUED.labels(device_type, cmd.command_type).inc()

    # 4. Produce to Kafka, keyed by device_id for per-device ordering.
    message = {
        "command_id": command_id,
        "device_id": cmd.device_id,
        "device_type": device_type,
        "command_type": cmd.command_type,
        "params": cmd.params,
        "issued_by": cmd.issued_by,
        "issued_at": issued_at.isoformat(),
    }
    try:
        future = get_producer().send(COMMAND_TOPIC, key=cmd.device_id, value=message)
        future.get(timeout=10)
    except KafkaError as e:
        cur.execute(
            "UPDATE commands SET status='FAILED', error_message=%s WHERE command_id=%s",
            (f"kafka publish failed: {e}", command_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        _mirror_status(command_id, "FAILED", cmd.device_id, cmd.command_type, error=str(e))
        COMMANDS_REJECTED.labels("kafka_error").inc()
        raise HTTPException(status_code=502, detail=f"Failed to publish command to Kafka: {e}")

    # 5. Mark dispatched. A fast device (or in-process edge driver) can ack via
    #    the broker before this update runs, so never downgrade an already-terminal
    #    status — only stamp dispatched_at and set SENT if still pending. RETURNING
    #    gives us the true resulting status to mirror.
    cur.execute(
        """
        UPDATE commands
           SET dispatched_at = COALESCE(dispatched_at, now()),
               status = CASE WHEN status IN ('ACKED', 'FAILED', 'COMPLETED')
                             THEN status ELSE 'SENT' END
         WHERE command_id=%s
        RETURNING status
        """,
        (command_id,),
    )
    final_status = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    _mirror_status(command_id, final_status, cmd.device_id, cmd.command_type)
    _persist_state(cmd.device_id, {
        "device_type": device_type,
        "last_command_id": command_id,
        "last_command_type": cmd.command_type,
        "last_command_status": final_status,
        "last_command_issued_at": issued_at.isoformat(),
    })
    COMMANDS_SENT.labels(device_type, cmd.command_type).inc()
    DISPATCH_LATENCY.observe(time.monotonic() - start)

    return {
        "command_id": command_id,
        "device_id": cmd.device_id,
        "device_type": device_type,
        "command_type": cmd.command_type,
        "status": final_status,
        "topic": COMMAND_TOPIC,
    }


@app.post("/commands", status_code=202)
def create_command(cmd: CommandRequest,
                   principal=Depends(require_role("operator")),
                   _rl=Depends(rate_limit("commands", 120, 60))):
    """Issue a command to a device. Requires operator (or admin). Audited + rate-limited.
    Phase 12: a tenant-scoped operator may only command its own tenant's devices."""
    _assert_tenant_access(principal, cmd.device_id)
    result = _dispatch_command(cmd)
    auth.audit(principal, "issue_command", f"{cmd.device_id}:{cmd.command_type}", "ok",
               device_id=cmd.device_id,
               detail={"command_id": result.get("command_id"), "issued_by": cmd.issued_by})
    return result


@app.get("/commands/{command_id}")
def get_command(command_id: str):
    # Fast path: Redis mirror.
    try:
        cached = REDIS.hgetall(_redis_status_key(command_id))
    except redis.RedisError:
        cached = None

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT command_id, device_id, device_type, command_type, params, status,
               issued_by, error_message, created_at, dispatched_at, acked_at
        FROM commands WHERE command_id = %s
        """,
        (command_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown command_id '{command_id}'")
    record = dict(row)
    record["command_id"] = str(record["command_id"])
    for ts in ("created_at", "dispatched_at", "acked_at"):
        if record.get(ts) is not None:
            record[ts] = record[ts].isoformat()
    record["live_status"] = cached.get("status") if cached else record["status"]
    return record


@app.get("/commands")
def list_commands(device_id: str | None = None, limit: int = 50):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if device_id:
        cur.execute(
            "SELECT command_id, device_id, command_type, status, created_at "
            "FROM commands WHERE device_id=%s ORDER BY created_at DESC LIMIT %s",
            (device_id, limit),
        )
    else:
        cur.execute(
            "SELECT command_id, device_id, command_type, status, created_at "
            "FROM commands ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["command_id"] = str(d["command_id"])
        d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return {"commands": out}


@app.post("/commands/{command_id}/ack")
def ack_command(command_id: str, ack: AckRequest,
                _p=Depends(require_role("service"))):
    """Device-execution feedback. Node-RED calls this after a device publishes
    its MQTT ack. Updates the Postgres audit row and the Redis status mirror."""
    status = ack.status.upper()
    if status not in ("ACKED", "FAILED"):
        raise HTTPException(status_code=422, detail="status must be ACKED or FAILED")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE commands
           SET status=%s, error_message=%s, acked_at=now()
         WHERE command_id=%s
        RETURNING device_id, device_type, command_type, created_at
        """,
        (status, ack.error, command_id),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown command_id '{command_id}'")
    device_id, device_type, command_type, created_at = row
    _mirror_status(command_id, status, device_id, command_type, error=ack.error)
    _persist_state(device_id, {
        "last_command_id": command_id,
        "last_command_type": command_type,
        "last_command_status": status,
        "last_command_error": ack.error,
        "last_command_acked_at": datetime.now(timezone.utc).isoformat(),
    })
    COMMANDS_ACKED.labels(device_type or "unknown", command_type, status).inc()
    ACK_LATENCY.labels(status).observe(
        (datetime.now(timezone.utc) - created_at).total_seconds())
    return {"command_id": command_id, "status": status}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
