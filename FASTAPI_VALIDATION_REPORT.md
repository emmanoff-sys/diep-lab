# FastAPI Service Validation Report (Static Review)

**Scope:** `/home/emmanoff_lab/projects/diep-lab/fastapi/app.py` (2156 lines), `fastapi/auth.py` (212 lines), `fastapi/requirements.txt`, `fastapi/Dockerfile`.
**Method:** Static code review only. Platform is DOWN; no app execution or network calls performed. Assumes TimescaleDB restoration completed successfully per `DIEP_PLATFORM_ASSESSMENT.md`.

---

## 1. Application Startup

The app is a **single-module FastAPI app** (`app.py`) with **no `@app.on_event("startup")` / lifespan hook**. All dependency clients are constructed at **import time** except the Kafka producer, which is lazy.

- **FastAPI app object**: `fastapi/app.py:22-28` — `title="DIEP API"`, `version="1.0.0"`, docs at `/docs`, `/redoc`, `/openapi.json`.
- **CORS middleware**: `fastapi/app.py:32-38` — origins from `DIEP_CORS_ORIGINS` (default `"*"`), `allow_credentials=False`, all methods/headers allowed.
- **DB config (eager, dict only — no connection at import)**: `fastapi/app.py:47-52`
  - `DB_HOST` (default `diep-timescaledb`)
  - `DB_NAME` (default `diep`)
  - `DB_USER` (default `diep`)
  - `DB_PASSWORD` (default `diep123`)
  - Same defaults are duplicated in `fastapi/auth.py:54-59` (`_DB` dict) — used only by `auth.audit()`.
- **Redis client (eager, constructed at import)**: `fastapi/app.py:91` — `REDIS = redis.Redis(host="diep-redis", port=6379, decode_responses=True)`. **Note**: this host is **hardcoded**, not read from `REDIS_HOST` env (unlike `auth.py:60`, which does read `REDIS_HOST`). A separate `redis.Redis` instance is constructed in `auth.py:60` with `host=os.getenv("REDIS_HOST", "diep-redis")`.
  - `redis.Redis(...)` itself is lazy-connecting (no handshake at construction), so import will not fail even if Redis is down — but `app.py`'s instance will never honor `REDIS_HOST` if it differs from `diep-redis`.
- **Kafka config (eager dict, lazy producer)**: `fastapi/app.py:55-71`
  - `KAFKA_BOOTSTRAP` (default `diep-kafka:9094`)
  - `KAFKA_SECURITY_PROTOCOL` (default `SASL_PLAINTEXT`)
  - `KAFKA_SASL_MECHANISM` (default `PLAIN`)
  - `KAFKA_SASL_USERNAME` (default `diep`)
  - `KAFKA_SASL_PASSWORD` (default `diep-kafka-pass-2026`)
  - `_kafka_security_kwargs()` (`fastapi/app.py:62-71`) builds `KafkaProducer` kwargs based on protocol; returns `{}` for plain `PLAINTEXT`.
  - `get_producer()` (`fastapi/app.py:214-225`) — module-global `_producer = None` (`fastapi/app.py:211`), constructed on first call to `get_producer()`. Comment explicitly states this is so the app "still starts if Kafka is briefly unavailable at boot" (`fastapi/app.py:208-210`).
- **auth.py module-level state** (imported via `import auth` at `fastapi/app.py:19`):
  - `AUTH_ENFORCED` = `DIEP_AUTH_ENFORCED` (default `"1"` → enforced) — `fastapi/auth.py:30`
  - `JWT_SECRET` = `DIEP_JWT_SECRET` (default `"diep-dev-jwt-secret-CHANGE-ME"`) — `fastapi/auth.py:31`
  - `JWT_TTL` = `DIEP_JWT_TTL` (default `3600`) — `fastapi/auth.py:32`
  - `REFRESH_TTL` = `DIEP_REFRESH_TTL` (default `30*24*3600`) — `fastapi/auth.py:33`
  - `API_KEYS` dict from `DIEP_SERVICE_TOKEN`, `DIEP_OPERATOR_KEY`, `DIEP_ADMIN_KEY` (each with `-CHANGE-ME` lab defaults) — `fastapi/auth.py:36-40`
  - `USERS` dict (JWT login) from `DIEP_ADMIN_USER`/`DIEP_ADMIN_PASSWORD`, plus `operator`/`viewer`/`acme-op`/`globex-op` with `DIEP_OPERATOR_PASSWORD`/`DIEP_VIEWER_PASSWORD`/`DIEP_ACME_PASSWORD`/`DIEP_GLOBEX_PASSWORD` — `fastapi/auth.py:44-52`
  - `_REDIS` (rate-limit store) from `REDIS_HOST` env (default `diep-redis`) — `fastapi/auth.py:60`
- **Dockerfile** (`fastapi/Dockerfile:23,27`): healthcheck hits `/healthz`; `CMD uvicorn app:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}`. Multi-worker means `_producer` global is per-process (each uvicorn worker gets its own lazily-created Kafka producer, own Redis client objects — fine since `redis.Redis` and `KafkaProducer` are not fork-shared here, app starts as separate processes).
- **Net effect on startup against a freshly-restored DB**: the app **will start successfully even if TimescaleDB, Redis, or Kafka are all down**, because no connection is attempted at import time and `get_conn()`/`get_producer()`/Redis calls are all per-request. `/healthz` will return 200 regardless. `/readyz` is the first place dependencies are actually probed.

---

## 2. Dependency Connections

### TimescaleDB (psycopg2)
- Connection helper: `get_conn()` — `fastapi/app.py:228-229` — `psycopg2.connect(**DB_CONFIG)`, called **per request**, no pooling/connection reuse. Every handler that touches the DB opens and closes its own connection (e.g. `_device_row` `fastapi/app.py:303-314`, `_latest_telemetry_for` `fastapi/app.py:317-327`, `_latest_command_for` `fastapi/app.py:330-341`, etc.)
- `auth.py` has its own separate `_DB` dict (`fastapi/auth.py:54-59`) and opens its own connection in `audit()` (`fastapi/auth.py:200-212`).
- Both `DB_CONFIG` (app.py) and `_DB` (auth.py) use identical env vars/defaults, so as long as `DB_HOST`/`DB_PASSWORD`/etc. are set consistently in `.env`, both modules connect to the same DB.
- Used extensively for: `devices`, `sites`, `telemetry`, `commands`, `alarms`, `derms_requests`, `analytics_events`, `device_onboarding`, `device_certifications`, `battery_assets`/`solar_assets`/`ev_chargers`, `audit_events` (via auth.audit).

### Redis
- Two separate clients exist:
  - `app.py` `REDIS` — `fastapi/app.py:91` — **hardcoded** `host="diep-redis"`, port 6379, `decode_responses=True`. Does NOT read `REDIS_HOST`.
  - `auth.py` `_REDIS` — `fastapi/auth.py:60` — `host=os.getenv("REDIS_HOST", "diep-redis")`.
- Key patterns:
  - `state:<device_id>` — device "twin" hash. Written by `_persist_state()` (`fastapi/app.py:285-300`, 24h TTL via `EXPIRE`), read by `_get_cached_state()` (`fastapi/app.py:275-282`). Populated on `/telemetry` POST (`fastapi/app.py:1917`) and on command dispatch/ack (`fastapi/app.py:2020-2026`, `2141-2147`).
  - `command:<command_id>` — command status mirror hash, 24h TTL. Written by `_mirror_status()` (`fastapi/app.py:232-252`), read by `GET /commands/{command_id}` (`fastapi/app.py:2056-2059`).
  - `ratelimit:<bucket>:<ident>:<window>` — fixed-window counter with `INCR`+`EXPIRE`, used by `auth.rate_limit()` (`fastapi/auth.py:175-190`); fails open if Redis errors.
  - `REDIS.info("replication")` — used by the onboarding "failover" certification test to check `connected_slaves` (`fastapi/app.py:1157`).
  - `/readyz` calls `REDIS.ping()` (`fastapi/app.py:169`).

### Kafka
- Producer config: `KAFKA_BOOTSTRAP` (default `diep-kafka:9094`), `KAFKA_SECURITY_PROTOCOL` (default `SASL_PLAINTEXT`), SASL mechanism/user/pass — `fastapi/app.py:55-71`. Matches the assessment's root-compose SASL/9094 listener configuration.
- `get_producer()` (`fastapi/app.py:214-225`) is lazily instantiated on first command dispatch — `acks="all"`, `retries=3`, JSON value serializer, UTF-8 key serializer.
- Topic: `COMMAND_TOPIC = "diep.commands"` (`fastapi/app.py:74`).
- Used only in `_dispatch_command()` (`fastapi/app.py:1986-1998`): `future = get_producer().send(COMMAND_TOPIC, key=cmd.device_id, value=message); future.get(timeout=10)`. On `KafkaError`, the command row is marked `FAILED`, Redis mirror updated, `COMMANDS_REJECTED{reason="kafka_error"}` incremented, and a `502` is raised (`fastapi/app.py:1988-1998`).
- **First Kafka connection attempt happens on the first `POST /commands` (or any DERMS endpoint that dispatches a command) after process start** — if Kafka/SASL listener 9094 is unreachable, `KafkaProducer(...)` construction itself may raise (not just `.send()`), and that exception is **not caught** by the `except KafkaError` block at `fastapi/app.py:1988` (constructor errors from `kafka-python` can raise `NoBrokersAvailable` etc. during `KafkaProducer.__init__`, which is not always a `KafkaError` subclass) — this would surface as an unhandled 500.

### InfluxDB
- **Confirmed retired from the FastAPI code path.** `grep -i influx` across `fastapi/` returns only **comments**:
  - `fastapi/app.py:87-89` — comment block: "InfluxDB retired from the API path — TimescaleDB is the authoritative telemetry store... A legacy Node-RED flow still writes an Influx 'smartmeter' measurement."
  - `fastapi/app.py:1831` — docstring on `latest_telemetry()`: "Latest telemetry row from TimescaleDB (was InfluxDB; retired in Phase 9-Data)."
  - `fastapi/requirements.txt:2` — comment: "InfluxDB removed in Phase 9-Data (TimescaleDB is the telemetry store)."
- No InfluxDB client library, connection config, or queries exist anywhere in `fastapi/`. Confirms the assessment's claim.

---

## 3. API Route Groups (all routes enumerated)

Auth roles per `auth.require_role(*allowed)` semantics (`fastapi/auth.py:129-138`): `admin` is superuser (passes any check); `service` only passes `"service"`; `operator` passes if `"operator"` or `"viewer"` in allowed; `viewer` passes only if `"viewer"` in allowed. If `DIEP_AUTH_ENFORCED=0`, every dependency is bypassed (`fastapi/auth.py:161-163`).

### Authentication
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| POST `/auth/token` | none | `LoginRequest{username,password}` | 200: `{access_token, refresh_token, token_type, role, tenant, expires_in}` / 401 invalid | Username/password → JWT access+refresh | app.py:100-114 |
| POST `/auth/refresh` | none | `RefreshRequest{refresh_token}` | 200: new access token / 401 invalid | Exchange refresh token for new access token | app.py:121-134 |
| GET `/auth/whoami` | viewer/operator/admin/service | — | 200: `{principal, role, auth}` | Identity introspection | app.py:137-140 |

### Health
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/healthz` | none | — | 200 always: `{status:"ok", instance}` | Liveness only, no dependency checks | app.py:147-151 |
| GET `/readyz` | none | — | 200 if DB+Redis OK else 503: `{ready, instance, checks:{database,redis}}` | Readiness (DB SELECT 1 + Redis PING) | app.py:154-177 |
| GET `/` | none | — | 200: `{platform:"DIEP", status:"UP"}` | Root banner | app.py:1806-1808 |
| GET `/health` | none | — | 200: `{status:"UP", platform:"DIEP"}` | Alias health endpoint | app.py:1811-1813 |
| GET `/version` | none | — | 200: `{platform, api_version, app_version, build}` | Build/version info | app.py:41-44 |
| GET `/metrics` | none | — | 200, `text/plain` Prometheus exposition | Prometheus scrape target | app.py:2154-2156 |

### Assets
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| POST `/assets` | admin | `AssetRegistration{device_id,device_type,location,site_name?,status?,tenant_id?,metadata?}` | 201: asset record (via get_asset) / 409 on dup | Register a new device + optional site | app.py:794-824 |
| GET `/assets` | viewer/operator/admin/service | — | 200: `{assets:[...]}` (tenant-scoped unless global principal) | List assets | app.py:827-847 |
| GET `/assets/{device_id}` | none | — | 200: asset record / 404 | Single asset detail | app.py:850-855 |
| GET `/assets/{device_id}/health` | none | — | 200: `{health, reason, ...}` / 404 | Per-asset health evaluation | app.py:869-875 |

### State
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/state/{device_id}` | none | — | 200: cached Redis state or DB-derived state / 404 | Live device state (twin) | app.py:858-866 |

### Fleet / Health (cross-cutting)
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/health/assets` | none | — | 200: `{assets:[{device_id, health}]}` | Health of all devices | app.py:878-893 |
| GET `/devices` | none | — | 200: `{devices:[...]}` | Raw device registry list | app.py:1816-1826 |
| GET `/fleet/overview` | none | — | 200: `{total_assets, by_device_type, by_site}` | Fleet-wide counts | app.py:1274-1295 |

### Onboarding
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| POST `/onboarding` | admin | `OnboardingEnrollment{device_id,site_name?,protocol?,vendor?,notes?}` | 201: onboarding record / 404 unknown device / 409 dup | Enroll device into onboarding pipeline | app.py:964-991 |
| GET `/onboarding` | none | query `status?` | 200: `{onboarding:[...]}` | List onboarding records, optional status filter | app.py:994-1017 |
| GET `/onboarding/{device_id}` | none | — | 200: onboarding record / 404 | Single device onboarding detail | app.py:1020-1025 |
| POST `/onboarding/{device_id}/validate` | admin | — | 200: onboarding record / 404 / 409 | REGISTERED→VALIDATED via checks | app.py:1047-1084 |
| POST `/onboarding/{device_id}/certify` | admin | — | 200: `{device_id, certified, failed_tests, pending_tests, results, onboarding}` / 404 / 409 | Run 6-test cert harness, VALIDATED→CERTIFIED | app.py:1204-1236 |
| POST `/onboarding/{device_id}/approve` | admin | `ApprovalRequest{approved_by?,notes?}` | 200: onboarding record / 404 / 409 | CERTIFIED→PRODUCTION_READY | app.py:1244-1271 |

### Sites
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/sites/overview` | none | — | 200: `{sites:[{site_name, site_type, latitude, longitude, asset_count, online_assets, latest_telemetry}]}` | All sites summary | app.py:1298-1333 |
| GET `/sites/{site_name}/overview` | none | — | 200: site detail w/ assets / 404 | Single site detail | app.py:1336-1369 |

### DERMS
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| POST `/derms/battery_dispatch` | operator (+rate_limit "derms" 60/60s) | `BatteryDispatchRequest{device_id?,site_name?,target_soc(0-100),max_power_kw?}` | 202: `{request_id, device_id, command_type, command}` / 404 / 422 | Dispatch battery toward target SOC | app.py:1397-1438 |
| POST `/derms/peak_shaving` | operator (+rate_limit "derms" 60/60s) | `PeakShavingRequest{site_name?,reduction_kw(>=0),max_power_kw?}` | 202 / 404 / 409 (low SOC) | Discharge battery to shave peak | app.py:1441-1471 |
| POST `/derms/demand_response` | operator (+rate_limit "derms" 60/60s) | `DemandResponseRequest{site_name?,event_duration_minutes(>=5),target_reduction_kw(>=0)}` | 202 / 404 / 409 | Battery discharge or EV stop_charging | app.py:1474-1510 |
| POST `/derms/load_optimization` | operator (+rate_limit "derms" 60/60s) | `LoadOptimizationRequest{site_name?,objective?,optimization_horizon_hours?}` | 202 / 404 | Charge/discharge battery per objective | app.py:1513-1548 |
| GET `/derms/requests` | none | query `limit?,request_type?` | 200: `{requests:[...]}` | List DERMS requests | app.py:1551-1577 |
| GET `/derms/requests/{request_id}` | none | — | 200 / 404 | Single DERMS request detail | app.py:1580-1598 |

### Analytics
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/analytics/forecast` | none | query `device_id?,site_name?,horizon_hours=24` | 200: `{device_id, device_type, horizon_hours, forecast:[...]}` / 404 / 422 | Linear-trend forecast of power/solar/SOC | app.py:1601-1613 |
| GET `/analytics/anomalies` | none | query `device_id?,site_name?,window_hours=24` | 200: `{device_id, window_hours, anomalies:[...]}` / 404 / 422 | 2-sigma power deviation + frequency-out-of-band detection | app.py:1616-1632 |
| GET `/analytics/predictive_maintenance` | none | query `device_id?,site_name?` | 200: insight / 404 / 422 | Maintenance risk score from failures/alarms/SOC | app.py:1635-1648 |
| GET `/analytics/summary` | none | query `site_name?` | 200: `{device_summary, analytics_event_count, site_name}` | Device/status counts + analytics event count | app.py:1651-1654 |
| GET `/recommendations` | none | query `site_name?,device_id?` | 200: `{recommendations:[...]}` | Aggregated operator recommendations | app.py:1685-1746 |

### Alarms
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/alarms` | none | query `device_id?,limit=50` | 200: `{alarms:[...]}` | List alarms | app.py:1657-1682 |

### Reports
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/reports/summary` | none | query `site_name?` | 200: aggregate report (device/command/derms/alarm counts + latest telemetry) | Operational summary report | app.py:1749-1803 |

### Telemetry (Commands group context but telemetry-specific)
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| GET `/telemetry/latest` | none | — | 200: latest telemetry row, or `{"message":"No telemetry found"}` | Most recent telemetry row across all devices | app.py:1829-1842 |
| POST `/telemetry` | service | `TelemetryPayload{device_id,time?,voltage,current,power_kw,frequency,solar_kw,battery_soc,grid_import_kw,grid_export_kw,power_factor?,energy_import_kwh?,energy_export_kwh?,temperature?,soh?,state?,extra?}` | 201: `{status:"created",device_id,time}` / 404 unknown device / 422 on insert error | Ingest a telemetry reading + mirror to Redis twin | app.py:1845-1928 |

### Commands
| Method/Path | Auth | Body | Response/Status | Purpose | Cite |
|---|---|---|---|---|---|
| POST `/commands` | operator (+rate_limit "commands" 120/60s) | `CommandRequest{device_id,command_type,params?,issued_by?}` | 202: `{command_id,device_id,device_type,command_type,status,topic}` / 404 unknown device / 422 invalid command_type / 502 Kafka failure | Issue device command, persist + produce to Kafka | app.py:2040-2050 |
| GET `/commands/{command_id}` | none | — | 200: command record + `live_status` from Redis / 404 | Command status lookup | app.py:2053-2082 |
| GET `/commands` | none | query `device_id?,limit=50` | 200: `{commands:[...]}` | List commands | app.py:2085-2110 |
| POST `/commands/{command_id}/ack` | service | `AckRequest{status,error?}` | 200: `{command_id,status}` / 404 / 422 (bad status) | Device-execution ack callback (from dispatcher/Node-RED) | app.py:2113-2151 |

**Total endpoint count: 36** (counting each method+path combination once).

---

## 4. curl Test Commands

Assumes `http://localhost:8000`, `DIEP_AUTH_ENFORCED=1`. Token placeholders correspond to `.env` variable names — substitute the real values from `/home/emmanoff_lab/projects/diep-lab/.env`.

### Authentication
```bash
# Login (no auth) — get JWT for "operator" role
curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"operator","password":"<DIEP_OPERATOR_PASSWORD>"}'

# Refresh access token (no auth header — token is in body)
curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token from /auth/token>"}'

# whoami — any of viewer/operator/admin/service token
curl -s http://localhost:8000/auth/whoami \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>"
```

### Health
```bash
curl -s http://localhost:8000/healthz
curl -s -i http://localhost:8000/readyz   # -i to see 200 vs 503
curl -s http://localhost:8000/
curl -s http://localhost:8000/health
curl -s http://localhost:8000/version
curl -s http://localhost:8000/metrics
```

### Assets
```bash
# Register asset — admin token (DIEP_ADMIN_KEY)
curl -s -X POST http://localhost:8000/assets \
  -H "Authorization: Bearer <DIEP_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"BAT002","device_type":"battery","location":"Abuja Site B","site_name":"Abuja Site A","status":"ONLINE","metadata":{}}'

# List assets — viewer/operator/admin/service token
curl -s http://localhost:8000/assets \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>"

# Get single asset — no auth required
curl -s http://localhost:8000/assets/BAT001

# Asset health — no auth required
curl -s http://localhost:8000/assets/BAT001/health
```

### State
```bash
curl -s http://localhost:8000/state/BAT001
```

### Fleet / Health
```bash
curl -s http://localhost:8000/health/assets
curl -s http://localhost:8000/devices
curl -s http://localhost:8000/fleet/overview
```

### Onboarding
```bash
# Enroll device — admin token
curl -s -X POST http://localhost:8000/onboarding \
  -H "Authorization: Bearer <DIEP_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"BAT001","site_name":"Abuja Site A","protocol":"sunspec","vendor":"Huawei","notes":"initial enrollment"}'

# List onboarding (optional status filter)
curl -s "http://localhost:8000/onboarding?status=REGISTERED"

# Get onboarding for device
curl -s http://localhost:8000/onboarding/BAT001

# Validate — admin token
curl -s -X POST http://localhost:8000/onboarding/BAT001/validate \
  -H "Authorization: Bearer <DIEP_ADMIN_KEY>"

# Certify — admin token
curl -s -X POST http://localhost:8000/onboarding/BAT001/certify \
  -H "Authorization: Bearer <DIEP_ADMIN_KEY>"

# Approve — admin token
curl -s -X POST http://localhost:8000/onboarding/BAT001/approve \
  -H "Authorization: Bearer <DIEP_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"approved_by":"jane.operator","notes":"production ready"}'
```

### Sites
```bash
curl -s http://localhost:8000/sites/overview
curl -s "http://localhost:8000/sites/Abuja%20Site%20A/overview"
```

### DERMS (operator token: DIEP_OPERATOR_KEY)
```bash
# Battery dispatch
curl -s -X POST http://localhost:8000/derms/battery_dispatch \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"BAT001","target_soc":80,"max_power_kw":10}'

# Peak shaving
curl -s -X POST http://localhost:8000/derms/peak_shaving \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"site_name":"Abuja Site A","reduction_kw":5,"max_power_kw":10}'

# Demand response
curl -s -X POST http://localhost:8000/derms/demand_response \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"site_name":"Abuja Site A","event_duration_minutes":30,"target_reduction_kw":5}'

# Load optimization
curl -s -X POST http://localhost:8000/derms/load_optimization \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"site_name":"Abuja Site A","objective":"maximize_solar","optimization_horizon_hours":2}'

# List/get DERMS requests — no auth
curl -s "http://localhost:8000/derms/requests?limit=10"
curl -s http://localhost:8000/derms/requests/<request_id>
```

### Analytics
```bash
curl -s "http://localhost:8000/analytics/forecast?device_id=BAT001&horizon_hours=24"
curl -s "http://localhost:8000/analytics/anomalies?device_id=METER001&window_hours=24"
curl -s "http://localhost:8000/analytics/predictive_maintenance?device_id=BAT001"
curl -s "http://localhost:8000/analytics/summary?site_name=Abuja%20Site%20A"
curl -s "http://localhost:8000/recommendations?site_name=Abuja%20Site%20A"
```

### Alarms
```bash
curl -s "http://localhost:8000/alarms?limit=20"
curl -s "http://localhost:8000/alarms?device_id=BAT001"
```

### Reports
```bash
curl -s "http://localhost:8000/reports/summary?site_name=Abuja%20Site%20A"
```

### Telemetry / Commands (service token: DIEP_SERVICE_TOKEN)
```bash
curl -s http://localhost:8000/telemetry/latest

# Ingest telemetry — service token
curl -s -X POST http://localhost:8000/telemetry \
  -H "Authorization: Bearer <DIEP_SERVICE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"METER001","voltage":230.1,"current":12.4,"power_kw":2.85,"frequency":50.0,"solar_kw":0.0,"battery_soc":62.5,"grid_import_kw":2.85,"grid_export_kw":0.0,"power_factor":0.98,"temperature":34.2,"state":"NORMAL","extra":{}}'

# Issue command — operator token
curl -s -X POST http://localhost:8000/commands \
  -H "Authorization: Bearer <DIEP_OPERATOR_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"EV001","command_type":"start_charging","params":{"limit_kw":7},"issued_by":"operator-test"}'

curl -s http://localhost:8000/commands/<command_id>
curl -s "http://localhost:8000/commands?device_id=EV001&limit=10"

# Ack a command — service token (normally called by dispatcher)
curl -s -X POST http://localhost:8000/commands/<command_id>/ack \
  -H "Authorization: Bearer <DIEP_SERVICE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"status":"ACKED"}'
```

---

## 5. `/healthz` vs `/readyz` Semantics

- **`GET /healthz`** (`fastapi/app.py:147-151`):
  - **No dependency checks at all.** Always returns HTTP 200 with `{"status": "ok", "instance": <HOSTNAME or "fastapi">}`.
  - Purpose stated explicitly in the docstring: liveness only, "never flaps the LB on a transient DB blip."
  - Used by the Dockerfile `HEALTHCHECK` (`fastapi/Dockerfile:22-23`) — meaning **the container healthcheck will report healthy even if TimescaleDB/Redis/Kafka are completely unreachable**.

- **`GET /readyz`** (`fastapi/app.py:154-177`):
  - Performs two real checks:
    1. `database`: `get_conn()` → `cursor.execute("SELECT 1")` → `fetchone()`. Any exception → `database: False`.
    2. `redis`: `REDIS.ping()` (the `app.py` Redis client, hardcoded to `diep-redis:6379`). Any exception → `redis: False`.
  - `ready = all(checks.values())` — **both** must be true.
  - Returns a raw `Response` with `application/json` body `{"ready": bool, "instance": ..., "checks": {"database": bool, "redis": bool}}`, **status code 200 if ready, 503 if not**.
  - **Does NOT check Kafka** — a Kafka outage will not be reflected in `/readyz` (consistent with the lazy-producer design), so an operator could see `/readyz` = 200 while `POST /commands` still fails with 502 (or worse, an unhandled 500 from `KafkaProducer.__init__`, see §6).

---

## 6. Code-Level Issues / Risks for a Freshly-Restored DB

1. **Hardcoded Redis host in `app.py` ignores `REDIS_HOST`** (`fastapi/app.py:91`): `REDIS = redis.Redis(host="diep-redis", port=6379, decode_responses=True)`. If the deployment ever sets `REDIS_HOST` to something other than `diep-redis` (e.g. for the HA `redis-replica`/`redis` split mentioned in the assessment), `auth.py`'s rate limiter and audit DB connect correctly via env, but the main app's state cache, command-status mirror, and `/readyz` Redis check will silently target the wrong (or nonexistent) host `diep-redis`, causing `/readyz` to report `redis: false` and all `_get_cached_state`/`_persist_state`/`_mirror_status` calls to fail (caught and ignored — see point 6 below) — degrading to DB-only behavior without obvious error.

2. **Kafka producer construction is not exception-safe in `_dispatch_command`** (`fastapi/app.py:1986-1998`): `get_producer()` calls `KafkaProducer(...)` (`fastapi/app.py:217-224`) on first use. If the SASL/9094 listener is down or credentials are wrong, `kafka-python`'s `KafkaProducer.__init__` can raise `NoBrokersAvailable` or other errors **during construction**, before `.send()` is even called. The `try/except KafkaError` block at `fastapi/app.py:1985-1998` only wraps the `send()`/`future.get()` call — `get_producer()` itself is called *inside* the `try`, but `KafkaProducer.__init__` failures may not subclass `KafkaError` in all kafka-python versions (e.g. `NoBrokersAvailable` does subclass `KafkaError` in 2.x, but other errors like SASL auth failures (`socket.error`, TLS errors) may not). Any non-`KafkaError` exception here would propagate as an **unhandled 500**, leaving the command row stuck in `PENDING` (it was already committed at `fastapi/app.py:1971`) with no `FAILED` status update or Redis mirror — `/commands/{id}` would show `PENDING` forever with no error context.

3. **Per-request DB connections, no pooling** (`fastapi/app.py:228-229`, used everywhere): every endpoint opens a fresh `psycopg2.connect()`. Under load (and with `UVICORN_WORKERS=2` per `fastapi/Dockerfile:26`) this could exhaust TimescaleDB's `max_connections` quickly, especially endpoints that issue multiple sequential queries with separate connections (e.g. `_predictive_maintenance_insight` opens 2 connections plus calls `_device_row`/`_get_cached_state`/`_state_from_db` which open more — `fastapi/app.py:536-585`). Not a startup blocker, but a scaling/restoration-load risk.

4. **`/readyz` doesn't check Kafka** (`fastapi/app.py:154-177`) — an operator following the assessment's recovery sequence (bring up `fastapi`, confirm `/readyz`, then issue a test `/commands`) could get a green `/readyz` while Kafka is still down, then hit a 502 (or possibly 500 per point 2) on the first `POST /commands`.

5. **CORS wide open by default** (`fastapi/app.py:32-38`): `DIEP_CORS_ORIGINS` defaults to `"*"`. Combined with `allow_credentials=False` this is relatively low-risk for cookie-based attacks (no cookies are used; auth is Bearer-token based), but it does mean any web origin can call read-only (unauthenticated) endpoints like `/devices`, `/fleet/overview`, `/telemetry/latest`, `/analytics/*`, `/alarms`, `/derms/requests` etc. Should be set explicitly in production via `.env`.

6. **Many Redis failures are silently swallowed** — `_persist_state` (`fastapi/app.py:296-300`), `_mirror_status` (`fastapi/app.py:246-252`), `_get_cached_state` (`fastapi/app.py:276-279`), and `auth.rate_limit` (`fastapi/auth.py:181-186`) all catch `redis.RedisError` and continue/return empty. This is by design (Redis is a "cache mirror, not source of truth" — comment at `fastapi/app.py:250-252`), but means a Redis outage degrades silently: rate limiting becomes a no-op (fail-open), `/state/{id}` falls back to DB-derived state (`fastapi/app.py:858-866`), and `/commands/{id}` `live_status` always equals `status` from Postgres.

7. **Schema columns referenced look consistent with `sql/000_schema.sql`/`001_commands.sql`** — spot-checked: `alarms.message`/`metadata`/`raised_at` (`fastapi/app.py:403,1663,1669` vs `sql/000_schema.sql:75,81-84`), `commands.command_id` as UUID cast to `str()` (`fastapi/app.py:2077,2107` vs `sql/001_commands.sql:7`), `devices.site_name`/`tenant_id` (`fastapi/app.py:811-815,832-843`). No obvious column-name mismatches found in this review against the schema files.

8. **Tenant scoping (`_assert_tenant_access`, `fastapi/app.py:778-791`) only applied to `POST /commands`** (`fastapi/app.py:2046`) — DERMS endpoints (`/derms/*`) accept `device_id`/`site_name` from tenant-scoped operators without an equivalent tenant check before dispatching commands via `_execute_derms_command` → `_dispatch_command`. A tenant-scoped `operator` (e.g. `acme-op`) could potentially dispatch DERMS actions against devices belonging to another tenant by specifying `site_name`/`device_id` of a different tenant's site, since `_select_device` (`fastapi/app.py:683-699`) and `_device_row` (`fastapi/app.py:303-314`) do not filter by tenant. This is a potential cross-tenant authorization gap, though it depends on whether `_dispatch_command` itself is tenant-aware (it is not — `fastapi/app.py:1931-2037`).

9. **`GET /assets/{device_id}`, `/state/{device_id}`, `/assets/{device_id}/health`, `/health/assets`, `/devices`, `/onboarding*` (GET), `/sites/*`, `/analytics/*`, `/alarms`, `/derms/requests*`, `/reports/summary`, `/commands` (GET), `/telemetry/latest` are all unauthenticated** even when `DIEP_AUTH_ENFORCED=1` — by design for dashboards/Grafana, but worth noting these expose full fleet/telemetry/command/DERMS/financial-relevant data without any token. CORS `*` (point 5) compounds this.

10. **No retry/backoff on `psycopg2.connect()`** anywhere — if TimescaleDB is still initializing (e.g. right after container start, before `pg_isready`), the *first* requests to almost any endpoint will raise unhandled `psycopg2.OperationalError` → unhandled 500 (FastAPI's default exception handler), since none of the DB-calling handlers wrap `get_conn()` in try/except for connection errors (only `register_asset`'s `IntegrityError` and `ingest_telemetry`'s general `Exception` around the INSERT are caught — `fastapi/app.py:817-821, 1918-1923`). `/readyz` is the only endpoint that gracefully reports DB-down as `503` rather than `500`.

---

## Summary

- **36 total HTTP routes/endpoints** identified across Authentication, Health, Assets, State, Fleet, Onboarding, Sites, DERMS, Analytics, Alarms, Reports, Telemetry, and Commands groups.
- App startup itself has **no hard dependency on DB/Redis/Kafka** — `/healthz` always returns 200; `/readyz` checks DB+Redis (not Kafka) and is the correct readiness gate per the recovery sequence in `DIEP_PLATFORM_ASSESSMENT.md`.
- InfluxDB is confirmed fully retired from `fastapi/` — only retired in code comments/docstrings, no live references.
- Biggest functional risks against a freshly-restored stack: (a) hardcoded `diep-redis` host in `app.py` bypassing `REDIS_HOST`, (b) potential unhandled 500 from `KafkaProducer` constructor errors on first `/commands` call if Kafka/SASL is unreachable, (c) no DB connection retry — early requests during TimescaleDB warm-up could 500 instead of a clean error, (d) `/readyz` doesn't cover Kafka so a green readiness check doesn't guarantee the command path works.
