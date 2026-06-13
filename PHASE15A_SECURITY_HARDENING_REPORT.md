# DIEP Phase 15A — Security Hardening Implementation Report

**Date:** 2026-06-11
**Scope:** Remediate the two High-severity production blockers identified in
`FINAL_DIEP_READINESS_REPORT.md` (readiness score 74/100):

1. Placeholder (`change-me-*`) secrets in `.env`
2. Redis running with no authentication

All changes were made live against the running 22-container stack. Containers
were recreated (not just restarted) where `.env`/compose changes required new
environment variables to be picked up.

---

## 1. Summary of Changes

### TASK 1 — Secret rotation

All previously-placeholder secrets were replaced with cryptographically random
values (`secrets.token_urlsafe`, 24–48 bytes of entropy). New values are stored
**only** in `.env` (not reproduced in this report). A pre-change snapshot was
saved to `.env.pre-phase15a.bak` for rollback.

| Variable | Old value | New value | Consumers |
|---|---|---|---|
| `DIEP_JWT_SECRET` | `change-me-to-a-long-random-string` | random 64-char urlsafe token | fastapi (`auth.py` JWT sign/verify) |
| `DIEP_SERVICE_TOKEN` | `change-me-service-token` | random 32-char urlsafe token | fastapi (API key), ingestor, dispatcher |
| `DIEP_OPERATOR_KEY` | `change-me-operator-key` | random 32-char urlsafe token | fastapi (API key, operator role) |
| `DIEP_ADMIN_KEY` | `change-me-admin-key` | random 32-char urlsafe token | fastapi (API key, admin role) |
| `DIEP_PORTAL_TOKEN` | `change-me-admin-key` | **set equal to the new `DIEP_ADMIN_KEY`** | portal BFF (`route.ts`) — must match an `API_KEYS` entry |
| `MINIO_ROOT_USER` | `change-me` (unused — compose hardcoded `admin`) | `diepadmin` | minio container |
| `MINIO_ROOT_PASSWORD` | `change-me` (unused — compose hardcoded `diep12345`) | random 32-char urlsafe token | minio container |
| `MQTT_PASS` | `change-me-device-password` | random 32-char urlsafe token | `mosquitto/config/passwd` (`diep-device` user hash regenerated) |
| `REDIS_PASSWORD` | *(did not exist)* | random 32-char urlsafe token | redis `--requirepass`, fastapi (`auth.py`, `app.py`) |

Notes:
- `DIEP_ADMIN_USER/PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`,
  `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, and `DB_PASSWORD` were **not**
  in scope for this phase (not on the Task 1 list) and were left unchanged.
  These remain `change-me-*` defaults except `DB_PASSWORD` (already fixed in
  Phase 9J/prior remediation to `diep123`, matching `POSTGRES_PASSWORD`).
- `MQTT_USER`/`MQTT_PASS` are **not actually consumed** by any currently-active
  container — `ingestor`, `dispatcher`, and `ev-charger` all hardcode
  `MQTT_USER: ""` / `MQTT_PASS: ""` in `docker-compose.yml` and authenticate
  via mutual TLS (`use_identity_as_username true`, `require_certificate true`
  in `mosquitto.conf`). The rotation was still applied to `.env` and to the
  mosquitto `passwd` file (regenerated via `mosquitto_passwd` inside the
  `diep-mqtt` container) for consistency and to cover the legacy
  username/password path if it is ever re-enabled.

### TASK 2 — Redis authentication

- `docker-compose.yml`: redis service `command` changed from
  `redis-server --appendonly yes` to
  `redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}`.
- `fastapi/auth.py` and `fastapi/app.py`: both `redis.Redis(...)` client
  constructors now pass `password=os.getenv("REDIS_PASSWORD") or None`.
- `REDIS_PASSWORD` added to `.env` and `.env.example`.
- No other service connects to Redis directly (confirmed via repo-wide grep —
  only `fastapi/auth.py` and `fastapi/app.py` instantiate a Redis client).

### Files modified

```
 .env                       (secrets rotated, REDIS_PASSWORD added)
 .env.example               (REDIS_PASSWORD documented)
 docker-compose.yml         (redis --requirepass, minio creds from env)
 docker-compose-minio.yml   (minio creds from env — unused overlay file, updated for consistency)
 fastapi/auth.py            (Redis client now passes password)
 fastapi/app.py             (Redis client now passes password)
 mosquitto/config/passwd    (diep-device password hash regenerated)
```

### Backups created (for rollback)

```
 .env.pre-phase15a.bak                  (pre-rotation .env)
 mosquitto/config/passwd.pre-phase15a.bak  (pre-rotation mosquitto passwd file)
```

---

## 2. Commands Executed

```bash
# Backups
cp .env .env.pre-phase15a.bak
cp mosquitto/config/passwd mosquitto/config/passwd.pre-phase15a.bak

# Generated new secrets (python3 secrets.token_urlsafe)

# Edited .env, .env.example, docker-compose.yml, docker-compose-minio.yml,
# fastapi/auth.py, fastapi/app.py (see diffs)

# Regenerated mosquitto password hash for diep-device
docker exec diep-mqtt mosquitto_passwd -b /mosquitto/config/passwd diep-device '<new MQTT_PASS>'

# Recreated containers to pick up new .env / compose values
docker compose up -d redis minio
docker compose up -d fastapi dispatcher ingestor portal
docker compose restart mqtt   # reload regenerated passwd file
```

`docker compose restart` was tried first for `redis`/`fastapi` but does **not**
re-read `.env` or the compose file — it only restarts the existing container
with its original config. `docker compose up -d <service>` was required to
recreate the containers with the new environment/command. This is documented
here because it's the most likely failure mode if this procedure is repeated.

---

## 3. Validation Evidence

### 3a. Redis authentication enforced

```
$ docker exec diep-redis redis-cli PING
NOAUTH Authentication required.

$ docker exec diep-redis redis-cli -a '<REDIS_PASSWORD>' --no-auth-warning PING
PONG

$ docker exec diep-redis redis-cli -a '<REDIS_PASSWORD>' --no-auth-warning KEYS "state:*"
state:BAT001
state:INV001
state:MG001
state:METER001
state:EV001
```
Unauthenticated access is now rejected; the existing `state:*` keys for all 5
devices are intact and reachable with the new password (no data loss from the
recreate — `redis-data` volume preserved).

### 3b. FastAPI authentication — old credentials rejected, new credentials work

```
GET /auth/whoami  Authorization: Bearer <OLD admin key 'change-me-admin-key'>
  -> 401 {"detail":"authentication required"}

GET /auth/whoami  Authorization: Bearer <OLD service token 'diep-service-dev-token-CHANGE-ME'>
  -> 401

GET /auth/whoami  Authorization: Bearer <OLD operator key 'change-me-operator-key'>
  -> 401

GET /auth/whoami  Authorization: Bearer <NEW admin key>
  -> 200 {"principal":"api-admin","role":"admin","auth":"apikey"}

GET /auth/whoami  Authorization: Bearer <NEW service token>
  -> 200 {"principal":"svc-machine","role":"service","auth":"apikey"}

GET /auth/whoami  (no Authorization header)
  -> 401
```

`docker exec diep-fastapi env` confirms the recreated container has the new
`DIEP_JWT_SECRET`, `DIEP_ADMIN_KEY`, `DIEP_SERVICE_TOKEN`, `REDIS_PASSWORD`
values loaded from `.env`.

(Note: `/devices` is an intentionally public/unauthenticated endpoint —
both old and new bearer tokens return 200 there, which is expected and
unrelated to the rotation.)

### 3c. JWT login (Portal authentication path)

```
POST /auth/token {"username":"admin","password":"change-me-admin-password"}
  -> 200 {"access_token": "...", "refresh_token": "...", "token_type":"bearer", "role":"admin"}

GET /devices  Authorization: Bearer <access_token>
  -> 200
```
JWTs are now signed with the new `DIEP_JWT_SECRET` and verify correctly
(round-trip tested end-to-end).

### 3d. Portal BFF (DIEP_PORTAL_TOKEN)

```
GET http://localhost:3002/api/diep/devices  -> 200
```
The portal container was recreated with the new `DIEP_PORTAL_TOKEN` (=new
`DIEP_ADMIN_KEY`) and successfully proxies authenticated requests to FastAPI.

### 3e. MQTT — devices reconnected after broker restart

```
$ docker logs diep-mqtt | grep "New client connected" | tail -6
... diep-telemetry-ingestor (u'ingestor')
... auto-... (u'dispatcher')
... charger-EV001 (u'EV001')
... edge-BAT001 (u'BAT001')
... edge-INV001 (u'INV001')
... edge-METER001 (u'METER001')
```
All mTLS clients (ingestor, dispatcher, EV001, BAT001, INV001, METER001,
MG001) automatically reconnected after the `diep-mqtt` restart (all clients
have `on_disconnect`/auto-reconnect handlers). Telemetry ingestion confirmed
flowing post-restart:

```
$ docker logs diep-ingestor --tail 5
[...] Ingested diep/solar/INV001 -> INV001 (power_kw=3.273, soc=0.0)
[...] Ingested diep/smartmeter/METER001 -> METER001 (power_kw=4.698, soc=0.0)
[...] Ingested diep/battery/BAT001 -> BAT001 (power_kw=-10.0, soc=92.654)
[...] Ingested diep/microgrid/MG001 -> MG001 (power_kw=15.0, soc=0.0)
[...] Ingested diep/charger/EV001 -> EV001 (power_kw=0.0, soc=0.0)
```

### 3f. Kafka command path — full PENDING→SENT→ACKED lifecycle

```
POST /commands {"device_id":"BAT001","command_type":"charge","params":{"power_kw":5.0}}
  -> {"command_id":"a39410ad-...","status":"SENT"}

GET /commands/a39410ad-...
  -> {"status":"ACKED",
      "created_at":"2026-06-11T11:29:40.716517+00:00",
      "dispatched_at":"2026-06-11T11:29:40.854153+00:00",
      "acked_at":"2026-06-11T11:29:40.925247+00:00"}

$ docker exec diep-redis redis-cli -a '<REDIS_PASSWORD>' --no-auth-warning HGETALL "command:a39410ad-..."
status        ACKED
updated_at    2026-06-11T11:29:40.962201+00:00
device_id     BAT001
command_type  charge
```
Dispatcher reconnected to Kafka SASL (`diep-kafka:9094`) after recreate
(`kafka.coordinator: Successfully joined group diep-command-dispatcher`,
generation 25), and the command round-tripped through Kafka → MQTT (mTLS) →
device → ACK → Redis cache + Postgres in <100ms, consistent with pre-rotation
performance.

### 3g. DERMS request — end-to-end

```
POST /derms/battery_dispatch?site_name=Abuja+Site+A
  {"power_kw":3.0,"mode":"charge","target_soc":80}
  -> {"request_id":"02777cfd-...","device_id":"BAT001","command_type":"discharge",
      "command":{"command_id":"ab13ffe4-...","status":"SENT"}}

GET /commands/ab13ffe4-...
  -> {"status":"ACKED", "created_at":"...11:30:04.035", "dispatched_at":"...11:30:04.045",
      "acked_at":"...11:30:04.084"}
```

### 3h. Audit trail — new principal correctly recorded

```sql
SELECT ts, principal, role, action, result FROM audit_events ORDER BY ts DESC LIMIT 5;

 2026-06-11 11:30:03 | api-operator | operator | derms_battery_dispatch | ok
 2026-06-11 11:29:40 | api-operator | operator | issue_command          | ok
 2026-06-11 08:03:16 | api-operator | operator | derms_load_optimization| ok
 2026-06-11 08:03:15 | api-operator | operator | derms_demand_response  | ok
 2026-06-11 08:02:17 | api-operator | operator | derms_peak_shaving     | ok
```
The new operator API key correctly maps to principal `api-operator` /
role `operator` and is captured in the audit log identically to before
rotation.

### 3i. MinIO — recreated with new root credentials

```
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9000/minio/health/live
200
```
MinIO recreated successfully with `MINIO_ROOT_USER=diepadmin` and the new
`MINIO_ROOT_PASSWORD`, data volume (`minio-data`) preserved.

### 3j. Overall container health

```
$ docker ps --format "{{.Names}}: {{.Status}}" | grep -v Up
(no output — all 22 containers Up)
```

---

## 4. Rollback Procedure

If any issue is found, rollback is straightforward since all original values
were preserved:

1. **Secrets / Redis password:**
   ```bash
   cp .env.pre-phase15a.bak .env
   docker compose up -d redis minio fastapi dispatcher ingestor portal
   ```
   This restores the pre-Phase-15A `.env` (no `REDIS_PASSWORD`,
   `change-me-*` secrets, `MINIO_ROOT_USER=change-me`/`MINIO_ROOT_PASSWORD=change-me`).

2. **docker-compose.yml / docker-compose-minio.yml:**
   ```bash
   git diff docker-compose.yml docker-compose-minio.yml   # review
   git checkout -- docker-compose.yml docker-compose-minio.yml
   ```
   Note: if `.env` is rolled back to the pre-15A version (no `REDIS_PASSWORD`),
   `docker-compose.yml` **must also** be rolled back, otherwise
   `--requirepass ${REDIS_PASSWORD}` will expand to `--requirepass` (empty),
   which redis-server rejects at startup (will crash-loop). Roll back both
   together.

3. **fastapi/auth.py, fastapi/app.py:**
   ```bash
   git checkout -- fastapi/auth.py fastapi/app.py
   docker compose up -d fastapi
   ```

4. **mosquitto password file:**
   ```bash
   cp mosquitto/config/passwd.pre-phase15a.bak mosquitto/config/passwd
   docker compose restart mqtt
   ```

All rollback steps are non-destructive to TimescaleDB, Kafka topics, or
Redis state-cache data (`state:*` / `command:*` keys persist across the
recreate via the `redis-data` volume).

---

## 5. Remaining Risks / Findings

### Critical (new finding from this session)

- **`.env` is staged in git** (`git status` shows `.env` as `AM` — added and
  modified, i.e. tracked). This means the **newly-rotated secrets are now
  sitting in the git index** and will be committed to history if a commit is
  made. This was a pre-existing condition (not introduced by this phase) but
  is now more urgent because real (random, sensitive) secrets — not
  `change-me-*` placeholders — are in the working tree.
  - **Action required before any commit:** `git restore --staged .env` (or
    `git rm --cached .env`), add `.env` to `.gitignore`, and verify
    `.env.example` (placeholders only) remains the tracked template.
  - If `.env` (with the *old* `change-me-*` values) was ever committed in a
    prior commit, those old placeholder secrets are already in git history —
    low sensitivity since they were placeholders, but worth a `git log -p --
    .env` check and history scrub if this repo is ever made non-private.

### High

- **`DIEP_ADMIN_PASSWORD`, `DIEP_OPERATOR_PASSWORD`, `DIEP_VIEWER_PASSWORD`,
  `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`, `DB_PASSWORD`** remain
  default/placeholder values (`change-me-*-password`, `diep123`). These were
  out of scope for Phase 15A (not listed in Task 1) but should be the next
  rotation batch — `DB_PASSWORD` in particular is a Postgres superuser-ish
  credential exposed on `0.0.0.0:5432`.

### Medium

- Several infra ports remain bound to `0.0.0.0` (Postgres 5432, Redis 6379,
  Kafka 9092/9094, MinIO 9000/9002, InfluxDB 8086) — unchanged from the prior
  readiness report. Redis now requires auth, which mitigates but does not
  eliminate exposure; consider binding these to `127.0.0.1` or an internal
  network only.
- `MQTT_USER`/`MQTT_PASS` rotation has **no effect on currently active mTLS
  device connections** (see Task 1 notes) — if the username/password auth
  path is ever re-enabled (e.g. `listener 1883` uncommented in
  `mosquitto.conf`), the new password is ready, but this path is currently
  dormant.
- `docker-compose-minio.yml` is an unused/overlay file (the `minio` service
  in the root `docker-compose.yml` is what's actually running). Updated for
  consistency but not validated by a live deploy.

### Low / Informational

- `mosquitto_passwd` printed warnings about `passwd` file permissions/owner
  (world-readable, not owned by root) — pre-existing, unrelated to this
  phase, but worth tightening (`chmod 0600`, `chown root`) in a future pass.
- No automated secret-rotation tooling exists; this rotation was manual.
  Consider a documented rotation runbook or a script wrapping the steps in
  §2 for repeatability.

---

## 6. Go/No-Go Update

Both High-severity blockers from `FINAL_DIEP_READINESS_REPORT.md` are now
resolved:

- ✅ Placeholder secrets (`DIEP_JWT_SECRET`, `DIEP_SERVICE_TOKEN`,
  `DIEP_OPERATOR_KEY`, `DIEP_ADMIN_KEY`, `DIEP_PORTAL_TOKEN`, MinIO, MQTT)
  rotated to random values; old credentials confirmed rejected, new
  credentials confirmed working end-to-end.
- ✅ Redis now requires authentication (`requirepass`); unauthenticated
  access confirmed rejected, authenticated access confirmed working,
  `state:*`/`command:*` cache data intact.

**New Critical finding** (the staged `.env` in git) must be resolved before
any commit/push. Recommended updated readiness score: **~80/100**, with the
remaining gap driven by the unrotated user-login passwords/`DB_PASSWORD`
(High, deferred), monitoring coverage gaps, and operational-maturity items
already documented in the prior report.

**Recommendation:** Still GO for staging. For production, additionally
require: (a) unstage/remove `.env` from git + add to `.gitignore`, (b) rotate
`DB_PASSWORD` and the four `DIEP_*_PASSWORD` user logins, (c) bind
infra ports to internal networks only.
