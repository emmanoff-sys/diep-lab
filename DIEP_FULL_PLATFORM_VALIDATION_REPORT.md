# DIEP Full Platform Validation Report — v1.0.0-pilot

**Date:** 2026-06-13
**Validator role:** Senior Platform Validation Engineer
**Scope:** End-to-end operational validation of the running DIEP stack (Docker Compose,
TimescaleDB, Redis, Kafka, MQTT/mTLS, FastAPI, Grafana, Prometheus, Alertmanager, MinIO,
Node-RED, Portal, DERMS simulators) on the Ubuntu pilot VM.
**Method:** Live commands executed against the running stack and the Git repository.
No production configuration modified, no data deleted, no services restarted.

---

## 1. Executive Summary

The DIEP v1.0.0-pilot stack is **largely healthy and operational**: all 24 containers are
up, the database/telemetry/monitoring/portal/API layers all pass their checks, the Git
repository is clean (the secrets/keys issue from the prior release-packaging review has
been resolved — `v1.0.0-pilot` is tagged on a clean 298-file commit with no secrets or
private keys), and backup/DR tooling is in place and verified.

However, **one critical defect was found during DERMS validation**: the `BAT001` battery
edge driver (SunSpec/Modbus simulator transport) fails every Modbus transaction with a
transaction-ID mismatch (`sent N, got N-1`). This causes:
- **Zero telemetry rows for BAT001** in the last 10 minutes (all other 4 devices have
  ~110-119 rows in the same window).
- **Every command issued to BAT001 ends in `FAILED`** status (full PENDING→SENT→ACKED
  pipeline executes correctly — Kafka → dispatcher → MQTT → device → ack → FastAPI — but
  the terminal device-side result is always a failure).
- Because **4 of the 5 DERMS scenarios route to BAT001** (it is the only registered
  battery asset), Battery Dispatch, Peak Shaving, Demand Response, and Microgrid/Load
  Optimization all complete their request lifecycle but result in `FAILED` commands.
- EV Charging has no dedicated DERMS endpoint and the `ev_chargers` table is empty, so it
  could not be exercised as a DERMS scenario.

**Readiness score: 80/100.** **Conditional GO** for continued pilot operation (telemetry,
monitoring, portal, API, backups all sound), but the BAT001 Modbus transport bug must be
fixed before the pilot relies on battery-dispatch DERMS commands.

---

## 2. Service Health Matrix

| Service | Container | Status | Notes |
|---|---|---|---|
| TimescaleDB | `diep-timescaledb` | ✅ Up | PG16.14, hypertable + 2 continuous aggregates active |
| Redis | `diep-redis` | ✅ Up | AUTH required and enforced |
| Kafka | `diep-kafka` | ✅ Up | Broker healthy; rebalance event at 16:16 self-recovered |
| Mosquitto (MQTT) | `diep-mqtt` | ✅ Up | mTLS (TLSv1.3) active on 8883 |
| FastAPI | `diep-fastapi` | ✅ Up | `/health`, `/readyz` = 200 |
| Portal | `diep-portal` | ✅ Up | Served on host port **3002** (not 3000) |
| Prometheus | `diep-prometheus` | ✅ Up | All 6 targets `up` |
| Grafana | `diep-grafana` | ✅ Up | `/api/health` database: ok |
| Alertmanager | `diep-alertmanager` | ✅ Up | Routing configured; receivers point to placeholder `.invalid` webhook URLs |
| postgres-exporter | `diep-postgres-exporter` | ✅ Up | Scraped by Prometheus |
| kafka-exporter | `diep-kafka-exporter` | ✅ Up | Scraped by Prometheus |
| node-exporter / cadvisor | `diep-node-exporter` / `diep-cadvisor` | ✅ Up (healthy) | |
| dispatcher / ingestor | `diep-dispatcher` / `diep-ingestor` | ✅ Up | Command lifecycle confirmed working |
| Edge simulators (EV/INV/MG/METER) | 4 containers | ✅ Up, telemetry flowing | ~110-119 rows/10min each |
| Battery edge (BAT001) | `diep-battery-edge` | ⚠️ Up but **failing** | Modbus transaction-ID mismatch on every read/write |
| MinIO | `diep-minio` | ✅ Up | Backup buckets populated |
| Node-RED | `diep-nodered` | ✅ Up (healthy) | High CPU (~25%) but stable |
| InfluxDB | `diep-influxdb` | ⚠️ Up (orphaned) | Known limitation, no longer in API path |
| Kafka UI | `diep-kafka-ui` | ✅ Up | |

**Containers:** 24/24 running, 0 unhealthy/restarting/exited at time of check.

---

## 3. Test Results

### 3.1 Repository validation — ✅ PASS

```
git status            → "nothing to commit, working tree clean"
git branch            → main (up to date with origin/main)
git tag -l            → v1.0.0-pilot
git ls-remote origin  → reachable (refs/heads/main resolved)
git log               → 1 commit: "Initial DIEP v1.0 pilot baseline"
```

The release-packaging gate from the prior `RELEASE_CERTIFICATION_REPORT.md` /
`GIT_SANITIZATION_INVENTORY.md` review has been **resolved**:
- HEAD commit contains **298 tracked files**, zero matches for
  `\.env$|\.key$|\.pem$|\.venv|\.coverage|passwd$|_credentialSecret|flows_cred`.
- `.gitignore` is committed.
- Remote `origin` (`git@github.com:emmanoff-sys/diep-lab.git`) is reachable via
  `git ls-remote`.

### 3.2 Infrastructure validation — ✅ PASS (with notes)

- Docker daemon: healthy, Server Version 29.1.3, 24/24 containers running, 0 paused/exited.
- Disk: 26G/48G used (56%), 21G available — healthy.
- Memory: **4.5 GiB / 7.2 GiB used, 1.9 GiB / 3.8 GiB swap in use** — host is under memory
  pressure; swap usage should be monitored on a 7.2 GiB pilot VM (see §5).
- `docker system df`: 19 images (10.79 GB, 99% reclaimable — i.e., mostly unused
  intermediate layers), 24 containers (268.9 MB), 15 volumes (1.526 GB).
- Top CPU consumers: `diep-nodered` (25.6%), `diep-cadvisor` (15.1%), `diep-kafka` (3.3%).

### 3.3 Database validation — ✅ PASS (BAT001 telemetry gap noted)

```sql
-- Hypertable
SELECT hypertable_name, num_dimensions FROM timescaledb_information.hypertables;
 telemetry | 1

-- Continuous aggregates
SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates;
 telemetry_1h | t
 telemetry_1m | t

-- Retention / compression jobs
policy_refresh_continuous_aggregate | telemetry_1m | every 5m  (start_offset 2h, end_offset 1m)
policy_refresh_continuous_aggregate | telemetry_1h | every 1h  (start_offset 1d, end_offset 1h)
policy_compression                  | telemetry    | every 12h (compress_after 7 days)
policy_retention                    | telemetry    | every 1d  (drop_after 90 days)
policy_retention                    | telemetry_1m | every 1d  (drop_after 180 days)
```

- Telemetry freshness (last 5 min): latest row at `2026-06-13 17:51:31` (0.66s old), 235
  rows total.
- `telemetry_1m` continuous aggregate up to date (`max(bucket) = 17:44:00`, within the
  5-minute refresh window).
- **Per-device telemetry in last 10 minutes:** EV001=119, METER001=119, INV001=119,
  MG001=110, **BAT001=0** (see §4, Issue 1).
- `commands` table: 9 historical commands (2026-06-11), all `ACKED` — full
  `created_at → dispatched_at → acked_at` lifecycle present, confirming the command
  pipeline previously worked end-to-end for BAT001 before the Modbus issue.

### 3.4 Redis validation — ✅ PASS

- `redis-cli ping` without auth → `NOAUTH Authentication required.` (auth enforced).
- `redis-cli -a <REDIS_PASSWORD> ping` → `PONG`.
- Write/read/delete round-trip on `validation:test` key succeeded.
- `state:*` keys present (5): `state:BAT001`, `state:EV001`, `state:INV001`,
  `state:METER001`, `state:MG001`.
- `command:*` keys: **none found**. Command state is tracked in the `commands` Postgres
  table (confirmed in §3.3), not in Redis — functionally fine, but if `command:*` Redis
  keys were an expected cache layer per design, this is a gap (informational only).

### 3.5 MQTT validation — ✅ PASS

- `diep-mqtt` container healthy; broker log shows active connections.
- mTLS listener (8883) active — all simulator and service clients negotiated
  **TLSv1.3 / TLS_AES_256_GCM_SHA384**: `edge-BAT001`, `edge-MG001`, `edge-METER001`,
  `charger-EV001`, `dispatcher`, `diep-telemetry-ingestor`.
- Telemetry messages flowing for EV001/INV001/MG001/METER001 (confirmed via DB rows in
  §3.3). BAT001 MQTT session connects with valid mTLS, but its telemetry payloads never
  reach the DB due to the Modbus failure upstream of the MQTT publish (see §4, Issue 1).
- Legacy plaintext ports 1883/9001 remain mapped to host (carried-forward known
  limitation, not a new finding).

### 3.6 Kafka validation — ✅ PASS

```
Topics: __consumer_offsets, diep.commands
Consumer group "diep-command-dispatcher" on diep.commands/partition 0:
  CURRENT-OFFSET=9  LOG-END-OFFSET=9  LAG=0
```

- Broker healthy, kafka-exporter scraping successfully.
- A coordinator heartbeat-expiry / rebalance event occurred at `16:16:28` (self-recovered
  by `16:16:32`, dispatcher rejoined the group automatically) — consistent with the
  previously documented Phase 15C single-broker fragility. No manual intervention was
  required this time.
- Command lifecycle: produced 4 new commands during DERMS testing (§3.10); all were
  consumed with zero lag and acknowledged back to FastAPI within ~50-300ms.

### 3.7 FastAPI validation — ✅ PASS

- `GET /health` → `200 {"status":"UP","platform":"DIEP"}`
- `GET /readyz` → `200 {"ready": true, "checks": {"database": true, "redis": true}}`
- `GET /docs`, `/openapi.json` → 200.
- `POST /auth/token` (admin credentials from `.env`) → 200, valid JWT issued.
- `GET /auth/whoami` (with JWT) → `{"principal":"admin","role":"admin","auth":"jwt"}`
- `GET /devices` (no auth) → 200, returns 5 devices — intentionally public read endpoint.
- `POST /derms/peak_shaving` (no auth) → **401** — DERMS mutation endpoints correctly
  require authentication.
- `GET /fleet/overview`, `/telemetry/latest` (with JWT) → 200.

### 3.8 Portal validation — ✅ PASS

- Portal container healthy; internal Next.js logs show successful `GET /api/diep/*`
  calls (health, assets, derms/requests all 200).
- **Note:** Portal is published on host port **3002**, not 3000 (`3000/tcp -> 3002`).
  `http://localhost:3002/` → 200, `/derms` route → 200,
  `/api/diep/health` → `{"status":"UP","platform":"DIEP"}`.
- Backend (FastAPI) connectivity confirmed via portal's own proxy logs.

### 3.9 Monitoring validation — ✅ PASS (Alertmanager receiver gap persists)

- Prometheus `/api/v1/targets`: all 6 targets `up` —
  `cadvisor`, `diep-fastapi`, `kafka-exporter`, `node-exporter`, `postgres-exporter`,
  `prometheus`.
- Grafana `/api/health` → `{"database":"ok","version":"13.0.2"}`.
- Alertmanager `/api/v2/status` → 200, cluster status `ready`, routing tree defined
  (`default` / `critical` / `warning` with severity-based routing and an inhibit rule).
- **However**, all 3 receivers (`default`, `critical`, `warning`) use
  `webhook_configs` pointing to `http://diep-alertmanager-webhook.invalid/*`
  (`alertmanager/alertmanager.yml`). These are placeholder URLs that will fail DNS
  resolution — **alerts are routed but not deliverable**. This matches the previously
  documented limitation ("Alertmanager has no notification receiver configured") — the
  routing/inhibition logic is now built out, but a real receiver endpoint is still
  needed before go-live.

### 3.10 DERMS validation — ⚠️ PARTIAL (pipeline OK, BAT001 device failure)

All requests used a fresh admin JWT from `/auth/token`.

| Scenario | Endpoint | Result | Outcome |
|---|---|---|---|
| Battery Dispatch | `POST /derms/battery_dispatch` `{"device_id":"BAT001","target_soc":80,"max_power_kw":10}` | HTTP 202, `command_type=charge`, `status=SENT` | Command `03fcf9ae…` → **FAILED** (acked in ~1.5s) |
| Peak Shaving | `POST /derms/peak_shaving` `{"reduction_kw":5,"max_power_kw":10}` (no `site_name` — see note) | HTTP 202, `command_type=discharge` | Command `2de234e1…` → **FAILED** (acked in ~60ms) |
| Demand Response | `POST /derms/demand_response` `{"event_duration_minutes":15,"target_reduction_kw":5}` (no `site_name`) | HTTP 202, `command_type=discharge` | Command `5e234037…` → **FAILED** (acked in ~50ms) |
| Microgrid/Load Optimization | `POST /derms/load_optimization` `{"objective":"maximize_solar","optimization_horizon_hours":2}` (no `site_name`) | HTTP 202, `command_type=charge` | Command `bd611a50…` → **FAILED**, error: `"control write failed: Modbus transaction id mismatch (sent 4184, got 4183)"` |
| EV Charging | `POST /derms/battery_dispatch` `{"device_id":"EV001",...}` | HTTP **422** `"device_id must be a battery asset"` | Not exercised — no dedicated EV-charging DERMS endpoint exists; `ev_chargers` table is empty |

**Note on `site_name`:** Peak Shaving, Demand Response, and Load/Microgrid Optimization
all returned **404** (`"No online battery available..."` / `"No DERMS-capable asset
available..."`) when called with `site_name: "Abuja Site A"` (the only row in the
`sites` table). Investigation found that **`devices.site_name` is `NULL`/empty for all
5 devices** (`devices_site_name_fkey` references `sites.site_name`, but no device row
has it populated), so the `_select_device()` site filter in `fastapi/app.py` never
matches. Omitting `site_name` from the request (it is optional) allows device selection
to fall back to "any online battery", which succeeded. **This is a data-seeding gap**:
site-scoped DERMS dispatch does not currently work for any site name, only the
unscoped/auto-select path.

**Command lifecycle (PENDING → SENT → ACKED):** Confirmed working end-to-end for all 4
executed commands — `dispatcher` logs show
`Received command from Kafka → Dispatched to MQTT → Device ack → Posted ack to FastAPI`,
and the `commands` table shows `created_at`, `dispatched_at`, and `acked_at` all
populated within ~50-1500ms. The **terminal status is `FAILED`** in all 4 cases because
the BAT001 device-side Modbus write fails (see §4, Issue 1) — this is a device/driver
defect, not a pipeline defect.

### 3.11 Backup & Recovery validation — ✅ PASS

- Scripts present and executable: `backup-db.sh`, `backup-config.sh`, `verify-backup.sh`,
  `install-backup-cron.sh`, `dr-test.sh`, `restore-db.sh`, `issue-device-cert.sh`.
- Latest DB dump: `backups/diep_20260613T042427Z.dump` (356 KiB,
  generated 2026-06-13 04:24Z). `sha256sum -c` against
  `diep_20260613T042427Z.dump.sha256` → **OK** (checksum matches).
- MinIO uploads confirmed:
  - `diep-backups/diep_20260613T042427Z.dump` (356 KiB)
  - `diep-config-backups/diep-config_20260613T042555Z.tar.gz` (40 KiB) + `.sha256`
- Cron jobs installed (`crontab -l`):
  - `0 2 * * *` → `backup-db.sh`
  - `30 2 * * *` → `backup-config.sh`
  - `0 3 * * 0` → `verify-backup.sh` (weekly; no run yet, log file not present —
    expected, first Sunday run pending)
- `restore-db.sh` present and executable; **not executed** (would require stopping/
  overwriting the live database — out of scope per validation rules).

### 3.12 Security validation — ✅ PASS (one informational finding)

| Check | Result |
|---|---|
| No secrets committed to Git | ✅ HEAD commit (298 files) contains zero `.env`/`.key`/`.pem`/`.venv`/`passwd`/credential-secret matches; `.gitignore` present and committed |
| Redis authentication | ✅ `NOAUTH` enforced without password; works with `REDIS_PASSWORD` |
| MQTT mTLS | ✅ TLSv1.3 client-cert auth confirmed for all edge/service clients on port 8883 |
| Kafka SASL | ✅ `SASL_PLAINTEXT` listener on port 9094 (`PLAIN` mechanism) configured alongside internal `PLAINTEXT` (9092, inter-broker/kafka-ui only) — see note below |
| JWT authentication | ✅ `/auth/token` issues HS256 JWT; protected DERMS endpoints return 401 without it, 202 with valid admin token |

**Note (informational):** The Kafka SASL `PLAIN` credentials
(`username="diep" password="diep-kafka-pass-2026"`) are **hardcoded directly in
`docker-compose.yml`**, which is committed to Git (`git show HEAD:docker-compose.yml`
contains this string twice). `SASL_PLAINTEXT` (not `SASL_SSL`) means this credential
travels unencrypted on the Docker bridge network. For a single-host pilot this is
low-risk (network is not externally reachable), but this credential should be:
(a) moved to `.env`/secrets management rather than hardcoded in compose, and
(b) rotated before any multi-host or production deployment that upgrades to
`SASL_SSL` (as already planned per the inline comment referencing the Strimzi manifest).

---

## 4. Issues Found

### Issue 1 — **BAT001 Modbus driver: transaction-ID mismatch on every transaction (Critical)**

`drivers/sunspec/transport.py:61` raises
`IOError(f"Modbus transaction id mismatch (sent {tx}, got {rx_tx})")` whenever the
simulated Modbus server's response transaction ID doesn't match the client's. In the
live `diep-battery-edge` logs, **every single telemetry read and command write for
BAT001 fails** with this error, off by exactly one (`sent N, got N-1`), recurring every
~5 seconds since at least 17:55. Impact:
- BAT001 has contributed **zero telemetry rows** in the last 10+ minutes (vs. 110-119
  for each other device).
- All 4 DERMS scenarios that dispatch to BAT001 (the only registered battery) complete
  their API/Kafka/MQTT/ack pipeline but end in `commands.status = 'FAILED'`.
- `state:BAT001` in Redis is stale (last good cached state, not updated by the failing
  driver).

**Likely cause:** an off-by-one in either the simulator's response-transaction-ID
echoing or the client's `_next_tx()` sequencing in `drivers/sunspec/transport.py`
(client increments `_tx` to N and sends it, but receives back N-1 — suggesting the
simulator may be echoing the *previous* request's transaction ID, e.g. a one-message
buffering/ordering bug on the simulator side).

### Issue 2 — **Site-scoped DERMS dispatch does not work for any site (Medium)**

`devices.site_name` is empty for all 5 devices, while `sites` contains `"Abuja Site A"`.
Any DERMS request that includes `site_name: "Abuja Site A"` (the documented/example
value, and the only real site) returns 404 (`"No online battery available..."` /
`"No DERMS-capable asset available..."`). Only the unscoped (no `site_name`) auto-select
path works. This should be fixed by backfilling `devices.site_name = 'Abuja Site A'` for
all 5 pilot devices.

### Issue 3 — **Alertmanager receivers are placeholder `.invalid` webhooks (Medium, carried forward)**

`alertmanager/alertmanager.yml` routes alerts to `default`/`critical`/`warning`
receivers, all pointing at `http://diep-alertmanager-webhook.invalid/*`. Routing logic
is correct, but no alert will actually be delivered. A real receiver (Slack/email/
PagerDuty/webhook) must be configured before pilot go-live.

### Issue 4 — **Kafka SASL credential hardcoded in committed `docker-compose.yml` (Low)**

See §3.12. Functional and low-risk for single-host pilot, but should move to
`.env`/secrets before wider deployment.

### Issue 5 — **Host memory pressure: 1.9 GiB of 3.8 GiB swap in use (Low/Informational)**

`free -h` shows 4.5/7.2 GiB RAM used plus 1.9 GiB swap in use on the pilot VM. Not
causing failures today, but headroom is limited for a 24-container stack; worth
monitoring via `node-exporter`/Grafana, especially if additional load is added.

### Issue 6 — **No dedicated EV-Charging DERMS endpoint (Low/Informational)**

The OpenAPI spec has no `/derms/ev_charging`-style endpoint, and `ev_chargers` table is
empty (EV001 exists only in `devices`). `POST /derms/battery_dispatch` explicitly
rejects non-battery `device_id`s (422). EV charging dispatch is therefore not currently
exercisable as a DERMS scenario through the API as designed in this validation's task
list — likely either an intentional v1.0 scope cut or a missing endpoint/seed data.

### Issue 7 — **Carried-forward known limitations (unchanged, not re-validated in depth)**

Per `RELEASE_NOTES_v1.0.md`/`PILOT_RELEASE_CHECKLIST.md`: 24h RPO (nightly dump only),
Kafka single-broker RF=1 (and a live rebalance event was observed during this session,
self-healed), 5 unrotated default secrets, no operator-facing TLS, orphaned
`diep-influxdb` container (confirmed still running), legacy plaintext MQTT ports
1883/9001 still mapped, floating `latest` image tags (confirmed: `apache/kafka:latest`,
`gcr.io/cadvisor/cadvisor:latest`, `grafana/grafana`, `minio/minio`, `nodered/node-red`,
`prom/alertmanager`, `prom/node-exporter`, `prom/prometheus`,
`provectuslabs/kafka-ui:latest`, `timescale/timescaledb:latest-pg16` — 10 of 17 distinct
images use floating tags).

---

## 5. Risk Assessment

| Risk | Severity | Likelihood | Status |
|---|---|---|---|
| BAT001 Modbus transaction-ID bug breaks battery telemetry + all battery-routed DERMS commands | **Critical** | Certain (currently occurring) | **New — must fix before relying on battery DERMS** |
| Site-scoped DERMS dispatch fails for the only configured site | Medium | Certain (currently occurring) | New — data-seeding fix (`devices.site_name`) |
| Alertmanager cannot deliver alerts (placeholder receiver URLs) | Medium | Certain | Carried forward, routing now built but receiver still missing |
| Kafka SASL credential hardcoded in committed compose file | Low | N/A | New — low risk on isolated pilot network |
| Host swap usage (1.9/3.8 GiB) under current load | Low | Ongoing | New — monitor, no impact observed yet |
| Kafka single-broker rebalance recurrence (Phase 15C) | Medium | Observed once this session, self-healed | Carried forward |
| 5 unrotated default secrets, no operator TLS, orphaned InfluxDB, floating image tags, 24h RPO | Medium/Low | Ongoing | Carried forward from `RELEASE_NOTES_v1.0.md` §5 |

---

## 6. Readiness Score: 80 / 100

| Category | Score | Rationale |
|---|---|---|
| Repository / release packaging | 10/10 | Clean tagged commit, no secrets, `.gitignore` in place — prior blocker resolved |
| Infrastructure | 8/10 | All containers up; memory/swap pressure noted |
| Database / telemetry | 7/10 | Hypertable, CAGGs, retention/compression all correct; BAT001 telemetry gap (-3) |
| Redis / MQTT / Kafka messaging | 9/10 | All healthy and authenticated; one self-healed Kafka rebalance |
| FastAPI / Portal / Auth | 10/10 | All endpoints and auth flows verified |
| Monitoring | 7/10 | Prometheus/Grafana fully up; Alertmanager receivers non-functional (-3) |
| DERMS functional scenarios | 4/10 | Pipeline (PENDING→SENT→ACKED) verified end-to-end, but **device-level result is FAILED for 4/5 scenarios** due to Issue 1; EV charging not exercisable (-6) |
| Backup & recovery | 10/10 | Scripts, cron, checksums, MinIO uploads all verified |
| Security | 9/10 | All required controls present; one hardcoded credential in compose (-1) |
| **Overall** | **80/100** (weighted) | |

This score is **independent of** the 88/100 platform-readiness score in
`PILOT_RELEASE_CHECKLIST.md` (which predates this end-to-end DERMS exercise) and the
now-resolved Git release-packaging gate in `RELEASE_CERTIFICATION_REPORT.md`.

---

## 7. GO / NO-GO Recommendation

**Conditional GO** for continued pilot operation of the platform's non-battery
functions (telemetry ingestion for EV/INV/MG/METER, monitoring, portal, API, backups,
Git release artifact) — these all passed validation cleanly.

**NO-GO for battery-dependent DERMS operations** (Battery Dispatch, Peak Shaving,
Demand Response, Microgrid/Load Optimization — i.e., 4 of the 5 DERMS scenarios) until:

1. **Issue 1 (Critical)** — the BAT001 Modbus transport transaction-ID mismatch in
   `drivers/sunspec/transport.py` / the SunSpec simulator is root-caused and fixed.
   Re-run this validation's §3.10 commands afterward and confirm `commands.status =
   'ACKED'` (not `FAILED`) and that BAT001 telemetry rows resume.
2. **Issue 2 (Medium)** — backfill `devices.site_name = 'Abuja Site A'` for all 5
   devices so site-scoped DERMS requests (the documented/expected usage pattern) work.
3. **Issue 3 (Medium, carried forward)** — configure a real Alertmanager receiver before
   any pilot incident depends on alert delivery.

Items 4-7 (Kafka SASL credential placement, swap headroom, Kafka single-broker
fragility, and the previously documented limitations) do not block continued pilot
operation but should be tracked alongside the existing `PILOT_RELEASE_CHECKLIST.md`
open items.

---

## 8. Related documents

- [`RELEASE_CERTIFICATION_REPORT.md`](RELEASE_CERTIFICATION_REPORT.md)
- [`GIT_SANITIZATION_INVENTORY.md`](GIT_SANITIZATION_INVENTORY.md)
- [`GIT_RELEASE_READINESS_REPORT.md`](GIT_RELEASE_READINESS_REPORT.md)
- [`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md)
- [`RELEASE_NOTES_v1.0.md`](RELEASE_NOTES_v1.0.md)
- [`DIEP_UAT_TEST_PLAN.md`](DIEP_UAT_TEST_PLAN.md)
