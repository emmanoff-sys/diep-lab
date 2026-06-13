# DIEP Platform Assessment

**Scope:** Read-only architecture, database, and recovery assessment of `docker-compose*.yml`, `sql/`, `backups/`, `fastapi/`, and `portal/`.
**Date:** 2026-06-11
**Status of environment at assessment time:** Platform is effectively **DOWN**. Only `diep-mqtt` (Mosquitto) is running; `diep-microgrid` is present but crash-looping (`Exited (255)`). All other services (TimescaleDB, Kafka, Redis, MinIO, FastAPI, Portal, Node-RED, ingestor, dispatcher, observability stack) are not running, though their named volumes still exist.

---

## A. Current Architecture

### A.1 Compose file landscape

The repo contains **two generations of Compose definitions** that are not fully reconciled:

1. **`docker-compose.yml` (root, monolithic/legacy)** — defines the *entire* original stack as one project (`diep-lab`), creating its own bridge network `diep-net` (not `external`). Services: `mqtt`, `kafka`, `kafka-ui`, `timescaledb`, `redis`, `minio`, `fastapi`, `nodered`, `dispatcher`, `portal`, `ingestor`, `influxdb`, `grafana`, `prometheus`, `alertmanager`, `cadvisor`, `node-exporter`, and 5 device simulators (`smartmeter`, `battery`, `solar`, `microgrid`, `ev-charger`). Many of these definitions are **pre-Phase-9J** — e.g. the `dispatcher`/`ingestor`/simulators here do **not** set `MQTT_PORT=8883` / `MQTT_TLS=1`, and `fastapi`/`dispatcher` Kafka config differs slightly from the split files.

2. **Per-service override files (`docker-compose-<service>.yml`)** — the current, actively-maintained split. Each declares `networks.default: { name: diep-lab_diep-net, external: true }` (or `diep-net` for a couple of older ones — `docker-compose-battery.yml`, `-ev-charger.yml`, `-microgrid.yml`, `-solar.yml`, `-fastapi.yml`, `-portal.yml`, `-ingestor.yml`, `-redis.yml`, `-minio.yml`, `-timescale.yml`, `-kafka.yml`, `-kafka-ui.yml`, `-alertmanager.yml`, `-cadvisor.yml` reference plain `diep-net`, while the **Phase 9J/9K/edge** files — `-ha.yml`, `-vault.yml`, `-sunspec.yml`, `-meter.yml`, `-battery-edge.yml`, `-microgrid-edge.yml`, `-ocpp.yml` — reference `diep-lab_diep-net`). This is an **inconsistent network reference** across files (see Risks).

3. **`docker-compose-twins.yml.disabled`** — a digital-twin service that exists but is intentionally disabled.

**⚠️ Network name mismatch is the single most consequential issue**: the root `docker-compose.yml` creates network `diep-net`; most split files expect external network `diep-lab_diep-net`; `docker network ls` currently shows `diep-lab_diep-net` exists (created previously), but `diep-net` does not. Bringing services up via different files inconsistently will either fail (`external network not found`) or silently create a second, disconnected network — splitting the platform into two networks that can't reach each other.

### A.2 Service inventory (logical, de-duplicated across files)

| Service | Image | Role | Port(s) |
|---|---|---|---|
| `mqtt` (mosquitto) | eclipse-mosquitto | Device telemetry/command bus | 8883 (mTLS only, per current `mosquitto.conf`); compose still maps 1883/9001 (stale) |
| `timescaledb` | timescale/timescaledb:latest-pg16 | Primary datastore (Postgres + TimescaleDB) | 5432 |
| `redis` | redis:7-alpine | Live state mirror (`state:` keys), command status cache | 6379 |
| `redis-replica` (HA) | redis:7-alpine | Read replica of `redis` | internal |
| `kafka` | apache/kafka | Command bus (`diep.commands` topic); SASL listener 9094 added in 9J-S5 | 9092 (PLAINTEXT), 9094 (SASL, app clients) |
| `kafka-ui` | provectuslabs/kafka-ui | Kafka admin UI | 8081 |
| `minio` | minio/minio | Object storage for DB backups (`diep-backups` bucket) | 9000 (S3 API), 9002 (console) |
| `vault` | hashicorp/vault (dev mode) | Secrets/PKI (lab demo) | 8200 |
| `fastapi` (+ `fastapi-2` for HA) | python:3.12 (custom Dockerfile exists but unused by compose `command:`) | Core REST API (auth, assets, telemetry, commands, DERMS, analytics, onboarding) | 8000 |
| `api-gw` (Caddy, HA) | caddy:2 | Reverse proxy / LB across `fastapi`+`fastapi-2`, HTTPS termination | 8090 (→8080 internal), 8443 |
| `dispatcher` | python:3.12 | Kafka → MQTT → FastAPI command dispatcher | n/a |
| `ingestor` | python:3.12 | MQTT → FastAPI `/telemetry` bridge | n/a |
| `portal` | node:20 (Next.js) | Operator web console (BFF via `/app/api/diep/[...path]`) | 3002 (→3000) |
| `nodered` | nodered/node-red | Legacy flow runner / command router, also writes legacy InfluxDB measurement | 1880 |
| `influxdb` | influxdb:1.8 | Legacy telemetry store — **retired from API path in Phase 9-Data**, only a stray Node-RED flow still writes to it | 8086 |
| `grafana` | grafana/grafana | Dashboards | 3001 |
| `prometheus` | prom/prometheus | Metrics scraping (incl. FastAPI `/metrics`) | 9090 |
| `alertmanager` | prom/alertmanager | Alert routing | 9093 |
| `cadvisor` | gcr.io/cadvisor | Container metrics | 8080 |
| `node-exporter` | prom/node-exporter | Host metrics | 9100 |
| Simulators: `smartmeter`, `battery`, `solar`, `microgrid`, `ev-charger` | python:3.12 | Legacy plaintext-MQTT device simulators (`./simulator`) | n/a |
| Edge drivers: `sunspec-edge`, `meter-edge`, `battery-edge`, `microgrid-edge`, `ocpp-csms` | python:3.12 | Phase 9C–9G "real protocol" simulators + edge agents, mTLS to MQTT | n/a |

### A.3 Data flows

**Telemetry (south → north):**
```
Device / simulator / edge driver
   → MQTT publish  diep/<domain>/<device_id>           (mTLS 8883, per-device cert)
   → ingestor (subscribes diep/+/+)
   → normalize payload → POST /telemetry  (Bearer DIEP_SERVICE_TOKEN)
   → FastAPI:
        - INSERT INTO telemetry (TimescaleDB hypertable)
        - Redis SET state:<device_id>  (powers /state, /assets/{id}/health, digital twins)
```

**Commands (north → south):**
```
Portal / API client
   → POST /commands (FastAPI, role-checked: operator/admin)
   → INSERT commands (PENDING) in Postgres
   → Kafka producer → topic "diep.commands" (SASL_PLAINTEXT, listener 9094)
   → dispatcher (Kafka consumer)
        → map device_type → MQTT domain (DOMAIN_MAP)
        → publish diep/<domain>/<device_id>/cmd (mTLS 8883)
   → device executes, publishes diep/<domain>/<device_id>/ack
   → dispatcher (subscribed diep/+/+/ack)
        → POST /commands/{command_id}/ack (Bearer DIEP_SERVICE_TOKEN)
   → FastAPI updates commands.status = ACKED|FAILED, Redis status cache, Prometheus counters
```

**DERMS / analytics flows:**
- `/derms/*` endpoints (battery_dispatch, peak_shaving, demand_response, load_optimization) write `derms_requests` rows and (per `DERMS_COMMANDS` metric) issue device commands via the same Kafka path.
- `/analytics/*` endpoints (forecast, anomalies, predictive_maintenance, summary) read from `telemetry`/`telemetry_1m`/`telemetry_1h` and write `analytics_events`.

**Portal:**
- Next.js app calls FastAPI through `portal/app/api/diep/[...path]/route.ts` (BFF), injecting `DIEP_PORTAL_TOKEN` (admin-scoped). Renders fleet, alarms, DERMS actions, twins, reports, administration.
- `NEXT_PUBLIC_GRAFANA_URL` embeds Grafana panels.

**Observability:**
- Prometheus scrapes FastAPI `/metrics`, node-exporter, cadvisor; Alertmanager handles alert routing; Grafana visualizes Prometheus + (legacy) InfluxDB.

**Backups:**
- `scripts/backup-db.sh`: `pg_dump -Fc` of `diep` DB → `backups/*.dump`, then uploaded to MinIO bucket `diep-backups` via `mc`.
- `scripts/restore-db.sh`: restores a dump into a scratch DB (`diep_restore_test`) for verification, using `timescaledb_pre_restore()/post_restore()`.

### A.4 MQTT flows (topic map)

| Topic pattern | Direction | Publisher | Subscriber |
|---|---|---|---|
| `diep/<domain>/<device_id>` | device → platform | simulators / edge drivers (sunspec, meter, battery, microgrid, ocpp-csms) | `ingestor` |
| `diep/<domain>/<device_id>/cmd` | platform → device | `dispatcher` | device / edge driver |
| `diep/<domain>/<device_id>/ack` | device → platform | device / edge driver | `dispatcher` |

Domains: `charger` (ev_charger), `battery`, `solar`, `microgrid`, plus meter (`smartmeter`/`MTR900`), with `TOPIC_ID_OVERRIDES` mapping `meter1` → `METER001` in the ingestor.

Broker auth model (current `mosquitto/config/mosquitto.conf`):
- `allow_anonymous false`, `password_file` + `acl_file`
- **Plaintext listeners 1883/9001 are commented out / retired.**
- **Only listener 8883 (mTLS) is active**, with `require_certificate true` and `use_identity_as_username true` (cert CN = MQTT identity).
- CA + server cert/key present at `mosquitto/config/certs/`. Per-device client certs present at `certs/devices/` for `MTR900`, `BAT900`, `INV900`, `MGC900`, `csms`, `ingestor`, `dispatcher` (no cert visible for `EV001`/legacy simulators — see Risks).

### A.5 Kafka flows

- Topic `diep.commands` (auto-created, replication factor 1, single broker/KRaft node).
- Two listener configurations exist depending on which compose file is used:
  - **Root `docker-compose.yml`** (current, active definition): `PLAINTEXT://9092`, `CONTROLLER://9093`, `SASL://9094` (SASL_PLAINTEXT, user `diep`/`diep-kafka-pass-2026`).
  - **`docker-compose-kafka.yml`** (older split file): PLAINTEXT-only on 9092/9093, **no SASL listener** — if used instead of root, FastAPI/dispatcher (which default to `diep-kafka:9094` + SASL) will fail to connect.
- `kafka-ui` connects to `diep-kafka:9092` (PLAINTEXT) for admin visibility regardless.
- Kafka data persisted to named volume `kafka-data`.

---

## B. Database Assessment

### B.1 Expected schema (from `sql/000_schema.sql` … `011_tenancy.sql`, applied in numeric order by `init-db.sh`)

**Required extension:**
- `timescaledb` (`CREATE EXTENSION IF NOT EXISTS timescaledb;`) — must be present in the `timescale/timescaledb:latest-pg16` image (it is, by default).

**Core tables:**
| Table | File | Purpose |
|---|---|---|
| `sites` | 000 | Site registry (name PK + unique index, type, lat/long) |
| `devices` | 000, 011 | Device registry; FK to `sites`; `tenant_id` added in 011 (FK to `tenants`, default `'default'`) |
| `solar_assets` | 000 | Solar inverter asset attributes (PK = `devices.device_id`) |
| `battery_assets` | 000 | Battery asset attributes |
| `ev_chargers` | 000 | EV charger asset attributes |
| `alarms` | 000 | Alarm log; reconciled with `message`/`metadata`/`raised_at` columns |
| `telemetry` | 000, 009 | **Hypertable**, partitioned on `time`. Base columns: voltage, current, power_kw, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw, metadata(jsonb). Extended (009): power_factor, energy_import_kwh, energy_export_kwh, temperature, soh, state |
| `commands` | 001 | Command audit (PENDING→SENT→ACKED/FAILED), FK to `devices` |
| `derms_requests` | 005 | DERMS dispatch/peak-shaving/demand-response/load-optimization request tracking |
| `analytics_events` | 006 | AI/analytics event log |
| `device_onboarding` | 007 | Onboarding lifecycle (REGISTERED→VALIDATED→CERTIFIED→PRODUCTION_READY) |
| `device_certifications` | 007 | Per-test certification results |
| `audit_events` | 008 | Append-only API audit trail |
| `tenants` | 011 | Multi-tenancy; seeded with `default`, `acme`, `globex` |

**Hypertables:**
- `telemetry` — `create_hypertable('telemetry', 'time', if_not_exists => TRUE)`. Indexes on `device_id` and `time DESC`.

**Continuous aggregates (`sql/010_data_lifecycle.sql`):**
- `telemetry_1m` — 1-minute rollup (avg/max/min power, avg voltage/frequency/solar/soc/temperature/power_factor, count). Refresh policy: start_offset 2h, end_offset 1m, every 5 min.
- `telemetry_1h` — 1-hour rollup, same metric set. Refresh policy: start_offset 1d, end_offset 1h, every 1h.
- Both created `WITH NO DATA` — **must be manually refreshed/backfilled** after restore if historical rollups are needed immediately (otherwise they populate only going forward via the policy).

**Compression & retention (also 010):**
- `telemetry` set to `timescaledb.compress`, segment by `device_id`, order by `time DESC`.
- Compression policy: chunks older than 7 days.
- Retention policies: `telemetry` 90 days; `telemetry_1m` 180 days. (`telemetry_1h` has no explicit retention — kept indefinitely.)

**Seed data (002–004):**
- Devices: `BAT001` (battery), `INV001` (solar_inverter), `MG001` (microgrid), `EV001` (ev_charger), `METER001` (smartmeter) — all site `Abuja Site A`.
- `Abuja Site A` site row (lat 9.0765, long 7.3986).
- Asset rows in `battery_assets`, `solar_assets`, `ev_chargers`.

### B.2 Idempotency / re-run safety
All DDL uses `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `ON CONFLICT DO NOTHING`, and continuous-aggregate/compression/retention policies use `if_not_exists => true`. **`init-db.sh` is safe to re-run** against an existing database — this is good for recovery.

### B.3 Backups present
- `backups/diep_20260605T235812Z.dump` (859,074 bytes)
- `backups/diep_20260605T235849Z.dump` (860,667 bytes)
- Both `pg_dump -Fc` custom-format dumps, ~5 days old relative to assessment date (2026-06-11). Two dumps 37 seconds apart suggests a backup script run twice in quick succession (or a retry) — sizes are nearly identical (~1.6KB difference), consistent with very low data volume at that point (lab/dev scale).
- **No evidence these were uploaded to MinIO** in the current state (MinIO is not running; bucket contents not verifiable from filesystem).
- **Risk:** dumps are 5+ days stale relative to "now" — any telemetry/commands/audit data ingested between 2026-06-05T23:58 and the platform going down is not in these backups (mitigated somewhat since the live `timescale-data` volume itself still exists, see C.1).

---

## C. Recovery Assessment

### C.1 Current platform state
- **Running:** `diep-mqtt` only (mosquitto 2.1.2, mTLS-only on 8883, healthy per logs).
- **Crash-looping:** `diep-microgrid` (legacy simulator) — `ConnectionRefusedError` connecting to MQTT on the port it expects (1883), because the active `mosquitto.conf` no longer serves plaintext 1883. This container is part of the **root `docker-compose.yml`** definition.
- **Stopped but data intact:** named volumes `diep-lab_timescale-data` (66.7 MB — contains the pre-existing Postgres data directory, not just the dump), `diep-lab_redis-data`, `diep-lab_minio-data`, plus (per last-known inventory) `diep-lab_kafka-data`, `diep-lab_grafana-data`, `diep-lab_influxdb-data`, `diep-lab_prometheus-data`. These volumes were last attached ~2026-06-08 per the `diep-lab_timescale-data` volume's `CreatedAt`/compose label.
- **Networks:** `diep-lab_diep-net` exists (bridge). The root-compose-only network `diep-net` does **not** currently exist.
- **Secrets:** `.env` is present (not `.env.example`) with `DIEP_AUTH_ENFORCED=1` and rotated-looking values for JWT/service/operator/admin tokens (good — not the shipped lab defaults). DB password placeholder appears overridden too (`DB_PASSWORD` not directly inspected for value but `.env` follows `.env.example` structure).
- **Inventory snapshots** (`inventory/docker-*.txt`) show a *previously* fuller running state (14 containers incl. fastapi, timescaledb, redis, minio, kafka, kafka-ui, prometheus, alertmanager, cadvisor, node-exporter, smartmeter, nodered, grafana, mqtt, influxdb) — i.e., the platform **was** up and is now mostly torn down, not "never started."

### C.2 Missing / inconsistent components
1. **Network name split** (`diep-net` vs `diep-lab_diep-net`) across compose files — must be resolved before a multi-file `docker compose -f ... -f ...` bring-up will work cleanly. The currently-existing network is `diep-lab_diep-net`.
2. **Root `docker-compose.yml` is stale relative to the split files** for at least: `mqtt` (no TLS volume mounts/cert paths matching the active mosquitto.conf — though it does mount `./mosquitto/config` which now contains the mTLS-only conf, creating the 1883-vs-8883 mismatch seen in the crash loop), `dispatcher`/`ingestor`/all 5 simulators (plaintext MQTT 1883, no certs — **will all fail to connect** against the current mosquitto.conf), `kafka` vs `docker-compose-kafka.yml` (SASL listener present in root, absent in split file).
3. **No MQTT client certs for the legacy simulators / `EV001`** — `certs/devices/` has certs for `MTR900, BAT900, INV900, MGC900, csms, ingestor, dispatcher` but not for the root-compose simulators (`smartmeter`/`METER001`, `battery`/`BAT001`, `solar`/`INV001`, `microgrid`/`MG001`, `ev-charger`/`EV001`) or for `nodered`. If the intent is to run the **edge-driver versions** (`*-edge.yml`, `ocpp-csms`) instead of the legacy simulators, this is fine; if both are expected to run, certs are missing for the legacy set.
4. **`docker-compose-twins.yml.disabled`** — digital twin service intentionally not wired in; `digitaltwin/app.py` exists but has no compose entry. Portal has `/twins` pages that may depend on it.
5. **Vault (`docker-compose-vault.yml`)** runs in **dev mode** (`server -dev`) — non-persistent, in-memory secrets store; if the platform's `.env` secrets are meant to be sourced from Vault, a restart loses them (dev mode has no unseal/persistence). Currently `.env` appears to hold the actual secrets directly, so this may be only a demo component.
6. **Stale leftover files**: `.docker-compose.yml.swp` (0-byte vim swap file — indicates an interrupted edit of `docker-compose.yml`), `prometheus/prometheus.yml.bak`, `nodered/.flows.json.backup`, `nodered/.config.*.backup`, `simulator/smartmeter.py.bak` — not blockers, but indicate in-progress/uncommitted edits worth reviewing before relying on the current `docker-compose.yml`.
7. **Git repo has zero commits** (`main` has no commits yet; everything is staged). There is no version history to diff against to confirm which compose file represents the "intended" current state — recovery decisions must be made from file content + running-state evidence alone.
8. **`.coverage`, `.venv/`, `nodered/node_modules/`, `portal/node_modules/`, `portal/.next/` are staged into git** — not a recovery blocker, but indicates the working tree/staging area needs cleanup (large/binary artifacts shouldn't be committed).

### C.3 Risks
- **Bringing up `docker-compose.yml` (root) as-is will reproduce the current crash loop** for `microgrid` and likely all other plaintext-MQTT simulators/dispatcher/ingestor, because the active Mosquitto config is mTLS-only on 8883 while these services are hardcoded to 1883 with no TLS material.
- **Mixed network names**: if some services are brought up via root compose (network `diep-net`) and others via split files (network `diep-lab_diep-net`), they will be on two separate Docker bridge networks and **unable to reach each other by container name**, even though container names/aliases look correct.
- **Kafka listener mismatch**: if `docker-compose-kafka.yml` (PLAINTEXT-only, no 9094/SASL) is used instead of the root definition, FastAPI and the dispatcher (both default to `diep-kafka:9094` + SASL_PLAINTEXT) will fail to produce/consume commands.
- **Continuous aggregates created `WITH NO DATA`**: after restoring `timescale-data` (or a `pg_dump`), `telemetry_1m`/`telemetry_1h` will be empty until their refresh policies run (5 min / 1 hour cadence) or a manual `CALL refresh_continuous_aggregate(...)` is issued — dashboards relying on these rollups will show gaps immediately after recovery.
- **Backup staleness**: the `backups/*.dump` files are ~5–6 days old; if `diep-lab_timescale-data` volume is lost/corrupted, recovery from these dumps loses any data after 2026-06-05T23:58Z. The volume itself (66.7MB, last touched ~2026-06-08) is the better recovery source if intact.
- **MinIO backup verification not possible** in current state (service down) — cannot confirm off-host copies of the dumps exist.
- **Mosquitto file permission warnings** (`passwd`/`acl` world-readable, wrong owner) — functional today but flagged by Mosquitto as a future hard-failure; should be fixed (`chmod 0700`, `chown mosquitto`) before a Mosquitto version upgrade.
- **Secrets in `.env` are tracked/staged in git** (`.env` shows as `A` in git status) — `.env` should typically be gitignored; if this repo/branch is pushed anywhere, live secrets (JWT secret, service/operator/admin tokens) would leak. This is a non-destructive *observation*, not something this assessment changes.

### C.4 Recovery sequence (recommended order)
1. **Decide and standardize on one network name** — given `diep-lab_diep-net` already exists and most of the actively-maintained Phase-9J+/HA/edge files reference it, standardize all compose files on `diep-lab_diep-net` (external). Root `docker-compose.yml` and the older split files (`-battery.yml`, `-solar.yml`, etc., which use bare `diep-net`) need their network blocks aligned.
2. **Decide which device layer is canonical**: legacy plaintext simulators (root compose: `smartmeter/battery/solar/microgrid/ev-charger`) **vs.** Phase 9C–9G mTLS edge drivers (`*-edge.yml`, `ocpp-csms`). Given Mosquitto is already mTLS-only, the edge-driver set is the one consistent with current security posture. The legacy simulator set would need either (a) re-enabling 1883 in `mosquitto.conf` (regression vs. 9J-S4 hardening) or (b) issuing client certs for `EV001`/`METER001`/`BAT001`/`INV001`/`MG001` and updating their compose definitions to use 8883+TLS like the edge drivers.
3. **Bring up data tier first**: `timescaledb`, `redis`, `kafka` (with the SASL/9094 listener config — i.e., the root-compose Kafka environment, not `docker-compose-kafka.yml`'s plaintext-only config), `minio`.
4. **Verify `diep-lab_timescale-data` volume integrity**: start `timescaledb` against the existing volume; check `pg_isready`, then `psql -c "\dt"` / `SELECT * FROM timescaledb_information.hypertables;` to confirm the schema and hypertable from B.1 are intact (read-only checks).
   - If the volume is missing/corrupt, fall back to `init-db.sh` (fresh schema) + `scripts/restore-db.sh` against the most recent dump in `backups/`.
5. **Run `init-db.sh`** regardless (it's idempotent) to ensure any schema migrations (008–011) not yet applied to the existing volume are applied.
6. **Manually refresh continuous aggregates** if recovering from a dump (`CALL refresh_continuous_aggregate('telemetry_1m', NULL, NULL)` etc., scoped to a sensible window) so `telemetry_1m`/`telemetry_1h` aren't empty.
7. **Bring up MQTT** (already running) — confirm cert paths in `mosquitto/config/certs/` match what `ingestor`/`dispatcher`/edge drivers expect (`ca.crt`, per-identity `.crt`/`.key` in `certs/devices/`).
8. **Bring up `fastapi`** — confirm `/healthz` then `/readyz` (DB + Redis checks) both pass before proceeding.
9. **Bring up `ingestor` and `dispatcher`** — confirm MQTT connects (mTLS) and Kafka connects (SASL/9094).
10. **Bring up device layer** (per decision in step 2) — confirm telemetry rows begin appearing in `telemetry` and `state:*` keys appear in Redis.
11. **Bring up `portal`**, `nodered` (if still desired — note its legacy InfluxDB write path), and observability stack (`prometheus`, `grafana`, `alertmanager`, `cadvisor`, `node-exporter`).
12. **Bring up `kafka-ui`, `vault`, HA components (`fastapi-2`, `redis-replica`, `api-gw`)** as optional/secondary.
13. **Smoke test**: `/healthz`, `/readyz`, `/devices`, `/telemetry/latest`, `/fleet/overview`, issue a test command via `/commands` and confirm it reaches `ACKED` via the dispatcher → MQTT → ack path.
14. **Re-run `scripts/backup-db.sh`** once stable to produce a fresh, current dump (closing the 5-day backup gap).

---

## D. Execution Plan (ordered checklist)

> All steps below are recommendations for the operator to execute; this assessment does not modify any files or run destructive commands.

1. [ ] Resolve `.docker-compose.yml.swp` — confirm whether `docker-compose.yml` has uncommitted intended edits (the swap file suggests an interrupted edit session); recover/discard as appropriate.
2. [ ] Reconcile network naming: update root `docker-compose.yml` and the bare-`diep-net` split files (`-battery.yml`, `-solar.yml`, `-microgrid.yml`, `-ev-charger.yml`, `-fastapi.yml`, `-portal.yml`, `-ingestor.yml`, `-redis.yml`, `-minio.yml`, `-timescale.yml`, `-kafka.yml`, `-kafka-ui.yml`, `-alertmanager.yml`, `-cadvisor.yml`) to use external `diep-lab_diep-net`, matching the 9J+/HA/edge files.
3. [ ] Decide canonical Kafka listener config (root-compose's SASL 9094 vs. `docker-compose-kafka.yml`'s plaintext-only) and remove/align the duplicate.
4. [ ] Decide canonical device layer (legacy plaintext simulators vs. Phase 9C–9G mTLS edge drivers) given Mosquitto is mTLS-only; issue missing per-device certs if legacy simulators are to be retained.
5. [ ] Start `timescaledb` against existing `diep-lab_timescale-data` volume; verify schema/hypertables/continuous aggregates exist (read-only `\dt`, `\d telemetry`, `timescaledb_information.*` queries).
6. [ ] Run `init-db.sh` (idempotent) to apply any pending migrations (008–011) and seeds.
7. [ ] If volume integrity check fails: restore from `backups/diep_20260605T235849Z.dump` (latest of the two) via `scripts/restore-db.sh`, then promote/import into the live `diep` DB.
8. [ ] Manually refresh `telemetry_1m`/`telemetry_1h` continuous aggregates for the recovered time range.
9. [ ] Start `redis`, `minio`, `kafka` (with SASL 9094), `kafka-ui`.
10. [ ] Start `fastapi`; confirm `/healthz` then `/readyz` return healthy (DB + Redis OK).
11. [ ] Start `ingestor`, `dispatcher`; confirm MQTT (mTLS) and Kafka (SASL) connections succeed in logs.
12. [ ] Start device layer per decision in step 4; confirm telemetry flowing into `telemetry` table and `state:*` Redis keys.
13. [ ] Start `portal`; confirm BFF (`/api/diep/[...path]`) reaches FastAPI and key pages (fleet, alarms, DERMS, twins, reports, administration) load.
14. [ ] Start `nodered` (review legacy InfluxDB-writing flow — decide retire or keep); start `influxdb`/`grafana`/`prometheus`/`alertmanager`/`cadvisor`/`node-exporter`.
15. [ ] Optional: start HA components (`fastapi-2`, `redis-replica`, `api-gw`/Caddy) and `vault` (note dev-mode caveat).
16. [ ] End-to-end smoke test: `/devices`, `/fleet/overview`, `/telemetry/latest`, issue a `/commands` request and confirm `ACKED` status round-trip.
17. [ ] Run `scripts/backup-db.sh` to produce a current backup and confirm MinIO upload succeeds.
18. [ ] Fix Mosquitto file-permission warnings (`chmod 0700` / `chown mosquitto` on `passwd`/`acl`).
19. [ ] Review git staging area: untrack `.env`, `.venv/`, `node_modules/`, `.next/`, `.coverage`, `*.bak`/`*.backup` files before any commit.
