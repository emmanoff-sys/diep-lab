# DIEP Phase 9-Data — Telemetry Data Lifecycle

> **Status:** Implemented and verified. Date: 2026-06-06. Additive + non-destructive —
> retention/compression windows set so nothing current is dropped; stack stayed intact
> (5/5 PRODUCTION_READY throughout).

---

## 1. Scope

Close out the data layer: **downsampling** (continuous aggregates), **compression**,
**retention**, **backups + verified restore**, and the long-standing **InfluxDB decision**.

---

## 2. Continuous aggregates (downsampling) — `sql/010_data_lifecycle.sql`

Two TimescaleDB continuous aggregates roll raw 5-second telemetry into time buckets, with
automatic refresh policies:

- **`telemetry_1m`** — 1-minute avg/min/max of power, plus avg voltage/frequency/solar/SoC/
  temperature/power_factor + sample count. Refresh every 5 min.
- **`telemetry_1h`** — 1-hour rollup (same metrics). Refresh hourly.

**Downsampling proven:** raw **55,903** rows → **4,735** (1m) → **105** (1h). Dashboards and
long-range queries hit the small aggregates instead of scanning raw — orders of magnitude
faster. Example (`telemetry_1h`, BAT900): `avg_power_kw=-29.56, avg_battery_soc=93.2,
avg_temperature=29.2, samples=476` per hour.

## 3. Compression

Native columnar compression enabled on `telemetry` (`segmentby device_id`,
`orderby time DESC`) with a policy to compress chunks **older than 7 days**. Current chunks
are <7 days old, so nothing compresses yet — the policy is registered and will run as data
ages (typically 90%+ storage reduction on time-series).

## 4. Retention

- Raw `telemetry`: drop **> 90 days** (tune to 7–30 days in prod once rollups are trusted).
- `telemetry_1m`: keep **180 days**. `telemetry_1h`: kept indefinitely.
- Data is only days old, so nothing is dropped now; the tiered policy (raw short, 1m medium,
  1h long) is in place.

**7 TimescaleDB policy jobs** registered (2× refresh, 1× compression, 2× retention, + system).

## 5. InfluxDB decision — **retire from the platform path**

InfluxDB was provisioned but the **FastAPI app never wrote to it** (only the legacy Node-RED
`smartmeter` flow does), while `/telemetry/latest` *read* from it. Decision and action:

- **Migrated `/telemetry/latest` to TimescaleDB** (the authoritative store).
- **Removed the Influx import + client init from `app.py`** — the API tier no longer depends
  on Influx at startup (verified: `/healthz`/`/readyz` green, no Influx connection).
- **Left `diep-influxdb` running** because a legacy Node-RED flow still writes to it;
  **to fully decommission**, remove the `influxdb out` node from the Node-RED flow
  (`nodered/flows.json`), then stop/remove the container. Flagged, not done (Node-RED flow
  change is out of this phase's scope).

Net: Influx is off the critical path; TimescaleDB is the single source of truth.

## 6. Backups + verified restore

- **`scripts/backup-db.sh`** — `pg_dump` (custom format) → verifies the dump's
  table-of-contents → uploads to **MinIO** (`s3://diep-backups/`). Verified: an 840 KiB dump
  landed in the bucket with `telemetry/devices/commands/audit_events` TABLE DATA present.
- **`scripts/restore-db.sh`** — restores into a **scratch database** using the documented
  TimescaleDB procedure (`timescaledb_pre_restore()` → `pg_restore` → `post_restore()`),
  compares row counts vs prod, then drops the scratch DB (never touches prod `diep`).
  Verified: `telemetry restored≈prod`, `devices 10=10`, etc. (tiny diffs = telemetry that
  kept flowing after the snapshot — correct point-in-time behaviour).

**Production note:** this logical backup **complements, not replaces, PITR** — continuous WAL
archiving + point-in-time recovery is configured via the CloudNativePG operator in
`k8s/postgres-cnpg.yaml` (9K). Schedule `backup-db.sh` via cron / a k8s CronJob; ship dumps
to versioned, lifecycle-policied object storage off-host.

---

## 7. Result

The telemetry data layer is complete: downsampled for fast queries, compression + retention
policies in place, backed up to object storage with a **verified restore**, and InfluxDB
retired from the platform path. No data loss, no breakage.

**Group A of the roadmap is now done except the security backlog** (9J-S4 mTLS, S5 Kafka
SASL, S6 TLS proxy, S7 Vault). Recommended next: **9J-S4 (per-device mTLS)** — the highest
remaining risk and the prerequisite for the SKIPPED certification `security` test — then
Group B (10A/10B orchestration + CI/CD) to deploy the 9K manifests on a real cluster.
