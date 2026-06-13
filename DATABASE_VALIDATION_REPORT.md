# DIEP Database Validation Report (Static Analysis)

**Mode:** Read-only static analysis. TimescaleDB is NOT running and was NOT started for this
report. All findings below are derived from inspecting `sql/000_schema.sql` … `sql/011_tenancy.sql`,
`init-db.sh`, `fastapi/app.py`, `fastapi/auth.py`, `ingestor/telemetry_ingestor.py`, and
`backups/*.dump`. This report describes the database state that **should** exist after either:

- (a) starting `diep-timescaledb` against the existing `diep-lab_timescale-data` volume, or
- (b) a fresh volume + `init-db.sh` + `scripts/restore-db.sh` against `backups/diep_20260605T235849Z.dump`.

Section 7 provides read-only SQL an operator can run against a live instance to confirm these
assumptions actually hold (no query in this report has been executed).

---

## 1. Schema files exist and are applied in order by `init-db.sh`

`/home/emmanoff_lab/projects/diep-lab/sql/` contains exactly 12 files, all present:

| # | File | Exists |
|---|---|---|
| 1 | `000_schema.sql` | yes |
| 2 | `001_commands.sql` | yes |
| 3 | `002_seed_battery_solar.sql` | yes |
| 4 | `003_seed_microgrid.sql` | yes |
| 5 | `004_seed_smartmeter.sql` | yes |
| 6 | `005_derms.sql` | yes |
| 7 | `006_analytics.sql` | yes |
| 8 | `007_onboarding.sql` | yes |
| 9 | `008_security.sql` | yes |
| 10 | `009_schema_extension.sql` | yes |
| 11 | `010_data_lifecycle.sql` | yes |
| 12 | `011_tenancy.sql` | yes |

`init-db.sh` (project root) applies them in this exact numeric order via a single piped `cat`:

```bash
cat sql/000_schema.sql sql/001_commands.sql sql/002_seed_battery_solar.sql \
    sql/003_seed_microgrid.sql sql/004_seed_smartmeter.sql sql/005_derms.sql \
    sql/006_analytics.sql sql/007_onboarding.sql sql/008_security.sql \
    sql/009_schema_extension.sql sql/010_data_lifecycle.sql sql/011_tenancy.sql \
  | docker exec -i diep-timescaledb psql -U diep -d diep
```

The script also waits for `pg_isready` (`docker exec diep-timescaledb pg_isready -U diep`) before
applying SQL — i.e., it requires the `diep-timescaledb` container to already be running and named
exactly `diep-timescaledb`.

**Ordering correctness:** The order matches dependency requirements — `000` creates `devices`,
`sites`, asset tables, `telemetry`/hypertable before `001` (which FK-references `devices` from
`commands` and seeds `EV001`); `002`–`004` seed devices that reference tables from `000`; `009`
(telemetry column extension) runs before `010` (continuous aggregates that read those new columns,
e.g. `avg(temperature)`, `avg(power_factor)`) — correct, since the aggregates would fail to
reference non-existent columns otherwise; `011` (tenancy) runs last, adding `tenant_id` to
`devices` after all seed inserts in `001`–`004` have already populated rows (those rows get the
column's `DEFAULT 'default'`).

---

## 2. Expected tables, defining files, and key columns

| Table | Defining file(s) | Key columns |
|---|---|---|
| `sites` | `000_schema.sql` (L6-30) | `site_name VARCHAR(100) PRIMARY KEY`, `site_type`, `latitude NUMERIC(9,6)`, `longitude NUMERIC(9,6)`, `created_at` |
| `devices` | `000_schema.sql` (L32-43), `011_tenancy.sql` (L18-22) | `id BIGSERIAL PK`, `device_id VARCHAR(50) UNIQUE NOT NULL`, `device_type`, `location`, `status DEFAULT 'UNKNOWN'`, `site_name FK→sites`, `created_at`, `tenant_id VARCHAR(50) NOT NULL DEFAULT 'default' FK→tenants` |
| `solar_assets` | `000_schema.sql` (L45-51) | `asset_id VARCHAR(50) PK FK→devices(device_id)`, `site_name FK→sites`, `capacity_kw REAL`, `status`, `created_at` |
| `battery_assets` | `000_schema.sql` (L53-59) | `asset_id VARCHAR(50) PK FK→devices(device_id)`, `capacity_kwh REAL`, `soc REAL`, `status`, `created_at` |
| `ev_chargers` | `000_schema.sql` (L61-67) | `charger_id VARCHAR(50) PK FK→devices(device_id)`, `site_name FK→sites`, `status`, `max_power_kw REAL`, `created_at` |
| `alarms` | `000_schema.sql` (L69-84) | `id BIGSERIAL PK`, `device_id FK→devices`, `alarm_type`, `severity`, `message TEXT`, `metadata JSONB`, `raised_at` |
| `telemetry` | `000_schema.sql` (L86-108), `009_schema_extension.sql` (L10-16) | hypertable on `time`; see §4 |
| `commands` | `001_commands.sql` (L5-23) | see §4 |
| `derms_requests` | `005_derms.sql` (L2-18) | `id BIGSERIAL PK`, `request_id UUID UNIQUE`, `request_type`, `site_name`, `device_id FK→devices`, `params JSONB`, `status DEFAULT 'CREATED'`, `created_at`, `executed_at`, `completed_at`, `error_message` |
| `analytics_events` | `006_analytics.sql` (L2-14) | `id BIGSERIAL PK`, `event_type`, `device_id FK→devices`, `site_name`, `severity DEFAULT 'INFO'`, `details JSONB`, `created_at` |
| `device_onboarding` | `007_onboarding.sql` (L4-20) | `id BIGSERIAL PK`, `device_id UNIQUE FK→devices`, `site_name`, `protocol`, `vendor`, `status DEFAULT 'REGISTERED'`, `validation JSONB`, `notes`, `registered_at`, `validated_at`, `certified_at`, `production_approved_at` |
| `device_certifications` | `007_onboarding.sql` (L22-32) | `id BIGSERIAL PK`, `device_id FK→devices`, `test_name`, `result`, `details JSONB`, `run_at` |
| `audit_events` | `008_security.sql` (L3-17) | see §4 |
| `tenants` | `011_tenancy.sql` (L5-16) | `tenant_id VARCHAR(50) PK`, `name`, `plan DEFAULT 'standard'`, `created_at` |

All 14 tables required by the task are accounted for.

---

## 3. Seed data — devices BAT001, INV001, MG001, EV001, METER001

| Device | Seeded in | device_type | site | Asset table row |
|---|---|---|---|---|
| `EV001` | `001_commands.sql` (L26-32) | `ev_charger`, location `'Abuja Site A'`, status `ONLINE` | `Abuja Site A` (via `location`) | `ev_chargers`: `charger_id='EV001'`, `site_name='Abuja Site A'`, `status='AVAILABLE'`, `max_power_kw=22` |
| `BAT001` | `002_seed_battery_solar.sql` (L5-12) | `battery`, location `'Abuja Site A'`, status `ONLINE` | `Abuja Site A` | `battery_assets`: `asset_id='BAT001'`, `capacity_kwh=100`, `soc=50`, `status='IDLE'` |
| `INV001` | `002_seed_battery_solar.sql` (L5-16) | `solar_inverter`, location `'Abuja Site A'`, status `ONLINE` | `Abuja Site A` | `solar_assets`: `asset_id='INV001'`, `site_name='Abuja Site A'`, `capacity_kw=10`, `status='ONLINE'` |
| `MG001` | `003_seed_microgrid.sql` (L5-12) | `microgrid`, location `'Abuja Site A'`, status `ONLINE` | `Abuja Site A` (also seeds the `sites` row: `site_type='microgrid'`, `latitude=9.0765`, `longitude=7.3986`) | none (no `microgrid_assets` table exists in schema) |
| `METER001` | `004_seed_smartmeter.sql` (L1-4) | `smartmeter`, location `'Abuja Site A'`, status `ONLINE` | `Abuja Site A` | none (smartmeter has no dedicated asset table) |

All inserts use `ON CONFLICT (...) DO NOTHING`, so they are idempotent and re-runnable.

**Note on ordering:** `001_commands.sql` seeds `EV001` and inserts into `ev_chargers` referencing
`site_name='Abuja Site A'` — but the `sites` row for `Abuja Site A` is not inserted until
`003_seed_microgrid.sql` (L10-12). Since `ev_chargers.site_name` and `devices.site_name` are
nullable FKs (no `NOT NULL`), and Postgres FK constraints are checked per-row at insert time
against the *current* table contents — at the time `001` runs, `sites` has zero rows, so the FK
constraint `ev_chargers.site_name REFERENCES sites(site_name)` would only succeed if `site_name`
were `NULL`. **However** `001` inserts the literal `'Abuja Site A'` into `ev_chargers.site_name`,
which IS NOT NULL — see Risk R1 in §8.

---

## 4. Detailed schema: `telemetry`, `devices`, `commands`, `audit_events`

### `telemetry` (hypertable; defined in `000_schema.sql` L86-108, extended in `009_schema_extension.sql` L10-16)

| Column | Type | Constraints / Default |
|---|---|---|
| `time` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` — hypertable partitioning column |
| `device_id` | `VARCHAR(50)` | `NOT NULL REFERENCES devices(device_id)` |
| `voltage` | `REAL` | nullable |
| `current` | `REAL` | nullable |
| `power_kw` | `REAL` | nullable |
| `frequency` | `REAL` | nullable |
| `solar_kw` | `REAL` | nullable |
| `battery_soc` | `REAL` | nullable |
| `grid_import_kw` | `REAL` | nullable (also re-added defensively at L103 via `ADD COLUMN IF NOT EXISTS`) |
| `grid_export_kw` | `REAL` | nullable (re-added defensively at L104) |
| `metadata` | `JSONB` | `DEFAULT '{}'::jsonb` (re-added defensively at L105) |
| `power_factor` | `double precision` | nullable (009, L11) |
| `energy_import_kwh` | `double precision` | nullable (009, L12) |
| `energy_export_kwh` | `double precision` | nullable (009, L13) |
| `temperature` | `double precision` | nullable (009, L14) |
| `soh` | `double precision` | nullable (009, L15) |
| `state` | `varchar(30)` | nullable (009, L16) |

Hypertable: `SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);` (000, L100).
Compression settings applied later (010) — see §5.

### `devices` (`000_schema.sql` L32-43, `011_tenancy.sql` L18-22)

| Column | Type | Constraints / Default |
|---|---|---|
| `id` | `BIGSERIAL` | `PRIMARY KEY` |
| `device_id` | `VARCHAR(50)` | `NOT NULL UNIQUE` |
| `device_type` | `VARCHAR(50)` | `NOT NULL` |
| `location` | `VARCHAR(128)` | nullable |
| `status` | `VARCHAR(50)` | `NOT NULL DEFAULT 'UNKNOWN'` |
| `site_name` | `VARCHAR(100)` | `REFERENCES sites(site_name)`, nullable (declared at L38, re-added defensively L42-43) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |
| `tenant_id` | `VARCHAR(50)` | `NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id)` (011, L18-20) |

### `commands` (`001_commands.sql` L5-19)

| Column | Type | Constraints / Default |
|---|---|---|
| `id` | `BIGSERIAL` | `PRIMARY KEY` |
| `command_id` | `UUID` | `NOT NULL UNIQUE` |
| `device_id` | `VARCHAR(50)` | `NOT NULL REFERENCES devices(device_id)` |
| `device_type` | `VARCHAR(50)` | nullable |
| `command_type` | `VARCHAR(50)` | `NOT NULL` |
| `params` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` |
| `status` | `VARCHAR(20)` | `NOT NULL DEFAULT 'PENDING'` (lifecycle: PENDING → SENT → ACKED \| FAILED) |
| `issued_by` | `VARCHAR(50)` | `NOT NULL DEFAULT 'api'` |
| `error_message` | `TEXT` | nullable |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |
| `dispatched_at` | `TIMESTAMPTZ` | nullable |
| `acked_at` | `TIMESTAMPTZ` | nullable |

### `audit_events` (`008_security.sql` L3-13)

| Column | Type | Constraints / Default |
|---|---|---|
| `id` | `BIGSERIAL` | `PRIMARY KEY` |
| `ts` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |
| `principal` | `VARCHAR(100)` | nullable — API key name or JWT subject |
| `role` | `VARCHAR(20)` | nullable — viewer \| operator \| admin \| service |
| `action` | `VARCHAR(50)` | `NOT NULL` — e.g. issue_command, derms_dispatch, register_asset |
| `resource` | `VARCHAR(200)` | nullable |
| `source_ip` | `VARCHAR(64)` | nullable |
| `result` | `VARCHAR(20)` | `NOT NULL` — ok \| denied \| error |
| `detail` | `JSONB` | `NOT NULL DEFAULT '{}'::jsonb` |

---

## 5. Indexes, FKs, hypertable, continuous aggregates, compression, retention

### Indexes (by table)

| Table | Index | Definition | File:Line |
|---|---|---|---|
| `sites` | `sites_site_name_idx` | `UNIQUE (site_name)`, created conditionally via `DO $$ ... $$` | 000:18-30 |
| `telemetry` | `telemetry_device_id_idx` | `(device_id)` | 000:107 |
| `telemetry` | `telemetry_time_idx` | `(time DESC)` | 000:108 |
| `commands` | `commands_device_id_idx` | `(device_id)` | 001:21 |
| `commands` | `commands_status_idx` | `(status)` | 001:22 |
| `commands` | `commands_created_at_idx` | `(created_at DESC)` | 001:23 |
| `derms_requests` | `derms_requests_request_type_idx` | `(request_type)` | 005:16 |
| `derms_requests` | `derms_requests_site_name_idx` | `(site_name)` | 005:17 |
| `derms_requests` | `derms_requests_device_id_idx` | `(device_id)` | 005:18 |
| `analytics_events` | `analytics_events_device_idx` | `(device_id)` | 006:12 |
| `analytics_events` | `analytics_events_site_idx` | `(site_name)` | 006:13 |
| `analytics_events` | `analytics_events_type_idx` | `(event_type)` | 006:14 |
| `device_onboarding` | `device_onboarding_status_idx` | `(status)` | 007:20 |
| `device_certifications` | `device_certifications_device_idx` | `(device_id)` | 007:31 |
| `device_certifications` | `device_certifications_run_idx` | `(run_at DESC)` | 007:32 |
| `audit_events` | `audit_events_ts_idx` | `(ts DESC)` | 008:15 |
| `audit_events` | `audit_events_principal_idx` | `(principal)` | 008:16 |
| `audit_events` | `audit_events_action_idx` | `(action)` | 008:17 |
| `devices` | `devices_tenant_idx` | `(tenant_id)` | 011:22 |

### Foreign keys

| Child table.column | References | File:Line |
|---|---|---|
| `devices.site_name` | `sites(site_name)` | 000:38, re-asserted 000:42-43 |
| `solar_assets.asset_id` | `devices(device_id)` | 000:46 |
| `solar_assets.site_name` | `sites(site_name)` | 000:47 |
| `battery_assets.asset_id` | `devices(device_id)` | 000:54 |
| `ev_chargers.charger_id` | `devices(device_id)` | 000:62 |
| `ev_chargers.site_name` | `sites(site_name)` | 000:63 |
| `alarms.device_id` | `devices(device_id)` | 000:71 |
| `telemetry.device_id` | `devices(device_id)` | 000:88 |
| `commands.device_id` | `devices(device_id)` | 001:8 |
| `derms_requests.device_id` | `devices(device_id)` | 005:7 |
| `analytics_events.device_id` | `devices(device_id)` | 006:5 |
| `device_onboarding.device_id` | `devices(device_id)` | 007:6 |
| `device_certifications.device_id` | `devices(device_id)` | 007:24 |
| `devices.tenant_id` | `tenants(tenant_id)` | 011:20 |

### Hypertable

```sql
SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);  -- 000_schema.sql:100
```

### Continuous aggregates (`010_data_lifecycle.sql`)

| Aggregate | Bucket | Source | Columns | Created with | Refresh policy |
|---|---|---|---|---|---|
| `telemetry_1m` | `time_bucket('1 minute', time)` | `telemetry`, `GROUP BY device_id, bucket` | `avg/max/min(power_kw)`, `avg(voltage)`, `avg(frequency)`, `avg(solar_kw)`, `avg(battery_soc)`, `avg(temperature)`, `avg(power_factor)`, `count(*) AS samples` | `WITH (timescaledb.continuous) ... WITH NO DATA` (010:6-22) | `add_continuous_aggregate_policy('telemetry_1m', start_offset=>'2 hours', end_offset=>'1 minute', schedule_interval=>'5 minutes', if_not_exists=>true)` (010:44-46) |
| `telemetry_1h` | `time_bucket('1 hour', time)` | same shape as above | same column set | `WITH (timescaledb.continuous) ... WITH NO DATA` (010:25-41) | `add_continuous_aggregate_policy('telemetry_1h', start_offset=>'1 day', end_offset=>'1 hour', schedule_interval=>'1 hour', if_not_exists=>true)` (010:48-50) |

Both are `MATERIALIZED VIEW IF NOT EXISTS ... WITH NO DATA` — they will contain **zero rows**
immediately after creation/restore until the refresh policy job runs (or a manual
`refresh_continuous_aggregate` call is issued).

### Compression policy (010:53-58)

```sql
ALTER TABLE telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => true);
```
Chunks containing data older than 7 days become compressed.

### Retention policies (010:60-63)

```sql
SELECT add_retention_policy('telemetry',    INTERVAL '90 days',  if_not_exists => true);
SELECT add_retention_policy('telemetry_1m', INTERVAL '180 days', if_not_exists => true);
```
`telemetry_1h` has **no retention policy** — kept indefinitely (intentional per comment at 010:24-25).

---

## 6. Required Postgres extensions

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;  -- 000_schema.sql:4
```

Only `timescaledb` is required by the SQL files. It ships by default in the
`timescale/timescaledb:latest-pg16` image referenced by the compose files (per the prior
assessment), so no separate installation step is needed beyond `CREATE EXTENSION`.

---

## 7. Post-Restore Verification Queries

Run these against the live `diep` database (read-only) after TimescaleDB is up, **without**
modifying any data.

### 7.1 Extension

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
```

### 7.2 Tables present (all 14)

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'sites','devices','solar_assets','battery_assets','ev_chargers','alarms',
    'telemetry','commands','derms_requests','analytics_events',
    'device_onboarding','device_certifications','audit_events','tenants'
  )
ORDER BY table_name;
```

### 7.3 Schema detail for the four key tables

```sql
\d+ telemetry
\d+ devices
\d+ commands
\d+ audit_events
```
(or via `information_schema.columns` for non-interactive use:)
```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='public' AND table_name = 'telemetry'
ORDER BY ordinal_position;
-- repeat for devices / commands / audit_events
```

### 7.4 Hypertable

```sql
SELECT * FROM timescaledb_information.hypertables
WHERE hypertable_name = 'telemetry';
```

### 7.5 Continuous aggregates

```sql
SELECT view_name, materialization_hypertable_name, finalized
FROM timescaledb_information.continuous_aggregates
WHERE view_name IN ('telemetry_1m', 'telemetry_1h');

-- Confirm whether they currently hold data (expect 0 rows immediately post-restore
-- if WITH NO DATA and policy hasn't run yet):
SELECT count(*) FROM telemetry_1m;
SELECT count(*) FROM telemetry_1h;
```

### 7.6 Continuous-aggregate refresh policies, compression policy, retention policies (background jobs)

```sql
SELECT job_id, application_name, schedule_interval, config, hypertable_name, proc_name
FROM timescaledb_information.jobs
WHERE hypertable_name IN ('telemetry', 'telemetry_1m', 'telemetry_1h')
   OR application_name ILIKE '%telemetry%'
ORDER BY job_id;

-- Job run history (confirm policies have actually executed):
SELECT job_id, last_run_status, last_successful_finish, next_start
FROM timescaledb_information.job_stats
WHERE job_id IN (SELECT job_id FROM timescaledb_information.jobs
                  WHERE hypertable_name IN ('telemetry','telemetry_1m','telemetry_1h'));
```

### 7.7 Compression status

```sql
SELECT hypertable_name, compression_enabled
FROM timescaledb_information.hypertables
WHERE hypertable_name = 'telemetry';

SELECT chunk_name, is_compressed
FROM timescaledb_information.chunks
WHERE hypertable_name = 'telemetry'
ORDER BY range_start DESC;
```

### 7.8 Indexes

```sql
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('sites','telemetry','commands','derms_requests','analytics_events',
                     'device_onboarding','device_certifications','audit_events','devices')
ORDER BY tablename, indexname;
```

### 7.9 Foreign keys

```sql
SELECT
    tc.table_name AS child_table,
    kcu.column_name AS child_column,
    ccu.table_name AS parent_table,
    ccu.column_name AS parent_column,
    tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name;
```

### 7.10 Seed devices and asset rows

```sql
SELECT device_id, device_type, location, status, site_name, tenant_id, created_at
FROM devices
WHERE device_id IN ('BAT001','INV001','MG001','EV001','METER001')
ORDER BY device_id;

SELECT * FROM battery_assets WHERE asset_id = 'BAT001';
SELECT * FROM solar_assets   WHERE asset_id = 'INV001';
SELECT * FROM ev_chargers    WHERE charger_id = 'EV001';

-- sites row
SELECT * FROM sites WHERE site_name = 'Abuja Site A';

-- tenants seed
SELECT tenant_id, name, plan FROM tenants ORDER BY tenant_id;
```

### 7.11 Quick row counts / sanity (read-only, cheap)

```sql
SELECT 'telemetry' AS tbl, count(*) FROM telemetry
UNION ALL SELECT 'commands', count(*) FROM commands
UNION ALL SELECT 'devices', count(*) FROM devices
UNION ALL SELECT 'audit_events', count(*) FROM audit_events
UNION ALL SELECT 'alarms', count(*) FROM alarms;
```

---

## 8. Discrepancies, ambiguities, and risks found in the SQL files

**R1 — `001_commands.sql` seeds `ev_chargers.site_name='Abuja Site A'` and `devices` rows with
`location='Abuja Site A'` before any row exists in `sites`.**
- `sites` is created empty in `000_schema.sql` (no seed rows).
- `001_commands.sql` (L26-32) inserts `devices(device_id='EV001', ..., location='Abuja Site A', ...)`
  — `location` is a plain `VARCHAR(128)`, not FK'd, so this is fine.
- However `001_commands.sql` (L30-32) inserts `ev_chargers(charger_id='EV001', site_name='Abuja Site A', ...)`,
  and `ev_chargers.site_name REFERENCES sites(site_name)` (000:63). At this point in the
  concatenated script (000 → 001 → 002 → 003 → 004), `sites` still has **zero rows** because the
  `Abuja Site A` site row is only inserted in `003_seed_microgrid.sql` (L10-12), which runs
  *after* `001`.
- **This means `init-db.sh`, run against a fresh database, should fail at the
  `INSERT INTO ev_chargers ...` statement in `001_commands.sql` with a foreign-key violation**
  (`insert or update on table "ev_chargers" violates foreign key constraint` — no row
  `'Abuja Site A'` in `sites`).
- This did not fail historically only if (a) the live DB volume already had a `sites` row from an
  earlier/partial run, or (b) the dump being restored already contains the `sites` row (so
  `restore-db.sh` + a DB that already has data wouldn't re-run `001` from scratch). On a **fresh
  volume + full `init-db.sh` run**, this ordering bug should reproduce. **Recommend**: move the
  `sites` seed insert from `003_seed_microgrid.sql` into `000_schema.sql` (or before `001`), or
  make `ev_chargers.site_name` nullable-safe by inserting `NULL` and backfilling later.
- Verify post-restore with: `SELECT * FROM sites;` and `SELECT * FROM ev_chargers WHERE charger_id='EV001';`
  — if both have rows, the FK was satisfied (meaning the existing volume/dump already has the site
  row from a prior successful run, masking this bug for *idempotent re-runs* but not for a
  from-scratch `init-db.sh`).

**R2 — `solar_assets.site_name` and `ev_chargers.site_name` FK to `sites`, but `battery_assets`
has no `site_name` column at all** (000:53-59). `battery_assets` therefore cannot be joined to
`sites` directly; any code doing per-site battery rollups must join via `devices.site_name`
instead. Not a bug, but an inconsistency between asset tables worth noting for analytics queries.

**R3 — No `microgrid_assets` table.** `MG001` (device_type `microgrid`) has no corresponding
asset table (unlike battery/solar/EV). If `fastapi/app.py` or the portal expects a
`microgrid_assets`-style table for `MG001` detail views, it is missing from the schema. Grep of
`fastapi/app.py` shows microgrid-specific data is read from `telemetry` (e.g. `pcc_kw` →
`grid_import_kw`/`grid_export_kw`/`power_kw` per the ingestor's `normalize()`,
`ingestor/telemetry_ingestor.py` L96-101) and `devices`/`sites`, not a dedicated asset table — so
this appears to be by design, not a gap.

**R4 — Continuous aggregates created `WITH NO DATA`.** `telemetry_1m`/`telemetry_1h` (010:6-41)
will be **empty** immediately after `init-db.sh` runs on a fresh DB, or after a `pg_dump`/`pg_restore`
cycle (continuous aggregate materialized data is restored as part of the dump if it existed, but a
fresh `WITH NO DATA` creation will not be). The refresh policies (5 min / 1 hour cadence) will
populate them going forward only. **Action**: after restore, if historical rollups are needed,
manually run:
```sql
CALL refresh_continuous_aggregate('telemetry_1m', NULL, NULL);
CALL refresh_continuous_aggregate('telemetry_1h', NULL, NULL);
```
(Verify emptiness first with the queries in §7.5.)

**R5 — `sites` table has a redundant self-referential `ALTER TABLE ... ADD COLUMN IF NOT EXISTS site_name`
(000:15-16) immediately after `site_name` was just declared as the `PRIMARY KEY` in the same
`CREATE TABLE` (000:7).** This is a no-op given `CREATE TABLE IF NOT EXISTS` already created the
column, but it's dead/confusing code — likely a leftover from reconciling "legacy sites tables
using integer PKs" per the comment at 000:14. Low risk, purely cosmetic; flagged for cleanup.

**R6 — Idempotency is generally good** (matches prior assessment B.2): all `CREATE TABLE`/`CREATE
INDEX`/`ADD COLUMN`/seed `INSERT` statements use `IF NOT EXISTS`/`ON CONFLICT DO NOTHING`, and the
continuous-aggregate/compression/retention policy calls all pass `if_not_exists => true`. The one
exception that breaks "always re-runnable from a totally empty DB" is **R1** above.

**R7 — Cross-check of `fastapi/app.py` / `auth.py` / `ingestor/telemetry_ingestor.py` against
schema — no missing columns found.**
- `INSERT INTO telemetry (time, device_id, voltage, current, power_kw, frequency, solar_kw,
  battery_soc, grid_import_kw, grid_export_kw, power_factor, energy_import_kwh,
  energy_export_kwh, temperature, soh, state, metadata)` (`fastapi/app.py` L1864-1870) — every
  column listed exists in the combined `000` + `009` schema. ✅
- `INSERT INTO commands (command_id, device_id, device_type, command_type, params, status,
  issued_by, created_at)` (`fastapi/app.py` L1964-1970) and the subsequent `UPDATE commands SET
  dispatched_at=..., status=...` (L2006-2010) and `UPDATE commands SET status=%s,
  error_message=%s, acked_at=now()` (L2126-2129) — all columns (`dispatched_at`, `acked_at`,
  `error_message`, `status`) exist in `001_commands.sql`. ✅
- `INSERT INTO audit_events (principal, role, action, resource, source_ip, result, detail)`
  (`fastapi/auth.py` L204-206) — matches `008_security.sql` columns exactly (all populated columns
  are nullable except `action`/`result`/`detail`, all of which are always supplied). ✅
- `INSERT INTO devices (device_id, device_type, location, status, site_name, tenant_id)`
  (`fastapi/app.py` L811) — `tenant_id` exists via `011_tenancy.sql` ALTER. ✅
- The ingestor's `EXTENDED_NUMERIC` fields (`power_factor`, `energy_import_kwh`,
  `energy_export_kwh`, `temperature`, `soh`) and `state` (`ingestor/telemetry_ingestor.py`
  L51-52, 110-112) all map onto the `009_schema_extension.sql` columns. ✅
- Device-specific long-tail fields (`vehicle_soc`, `connector_status`, `session_energy_kwh`,
  `load_kw`, `setpoint_kw`, `grid_connected`, `mode` — ingestor L54-55) are packed into
  `telemetry.metadata` JSONB (`out["extra"]`, ingestor L122-124), consistent with the JSONB
  `metadata` column (000:97, 105). ✅

No column-naming or type mismatches were found between the application code and the schema files.

---

## 9. Backup files present and staleness

```
backups/diep_20260605T235812Z.dump   859,074 bytes   (2026-06-05T23:58:12Z)
backups/diep_20260605T235849Z.dump   860,667 bytes   (2026-06-05T23:58:49Z)
```

- Both are `pg_dump -Fc` custom-format dumps (per `scripts/backup-db.sh`, per prior assessment).
- The task references restoring from `backups/diep_20260605T235849Z.dump` — this **is** the
  newer/larger of the two (860,667 bytes vs 859,074 bytes), 37 seconds apart from its sibling.
- **Staleness**: relative to "now" (2026-06-11), both dumps are **~5 days, 6 hours old**
  (2026-06-05T23:58 → 2026-06-11). Any `telemetry`, `commands`, `alarms`, `audit_events`,
  `derms_requests`, or `analytics_events` rows written after 2026-06-05T23:58:49Z are **not**
  present in either dump.
- The `diep-lab_timescale-data` volume (66.7MB, last touched ~2026-06-08 per the prior assessment)
  postdates these dumps by ~2.5 days and is therefore the preferred recovery source if intact —
  restoring from the dump instead would lose roughly 2.5 days of telemetry/audit data relative to
  the volume's last write.
- No newer dumps (`*.dump` dated after 2026-06-05) exist in `backups/`.
- Post-restore, recommend confirming data recency with:
  ```sql
  SELECT max(time) FROM telemetry;
  SELECT max(created_at) FROM commands;
  SELECT max(ts) FROM audit_events;
  ```
  and comparing against the expected dump/volume timestamp to confirm which source was actually
  used and how much data gap (if any) resulted.
