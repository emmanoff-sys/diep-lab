# DIEP Deployment Remediation Report

**Date:** 2026-06-15
**Role:** Release Engineering Lead
**Input:** [`DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) (2026-06-15,
independent "clean clone, docs-only" deployment of `v1.0.0-pilot`), findings F1-F5.
**Objective:** Make a fresh GitHub clone deployable per the published documentation
without tribal knowledge, manual database surgery, or missing artifacts.

All changes in this report are made to the working tree of
`~/projects/diep-lab` (uncommitted at the time of writing). They do **not** alter the
running `diep-*` production containers — postgres/mqtt/etc. are not restarted, and no
database is modified by this report. [`DEPLOYMENT_REVALIDATION_REPORT.md`](DEPLOYMENT_REVALIDATION_REPORT.md)
re-runs the full clean-deploy walkthrough against this remediated tree in a separate
workspace to confirm the fixes close out F1-F4.

---

## F1 — `DB_PASSWORD` mismatch (CRITICAL)

**Problem:** `docker-compose.yml`'s `timescaledb` service hardcoded
`POSTGRES_PASSWORD: diep123`, while `.env.example`'s `DB_PASSWORD` (consumed by
`fastapi`/`ingestor`/`dispatcher`/`postgres-exporter`) defaulted to
`change-me-db-password`. On a fresh deploy following `cp .env.example .env`, these never
matched, so `/readyz` permanently reported `{"database": false}`.

**Fix:**
- [`docker-compose.yml`](docker-compose.yml) — `timescaledb.environment` now reads
  `POSTGRES_DB: ${DB_NAME:-diep}`, `POSTGRES_USER: ${DB_USER:-diep}`,
  `POSTGRES_PASSWORD: ${DB_PASSWORD:-change-me-db-password}`. Docker Compose
  substitutes these from the top-level `.env` file automatically (no `env_file:`
  needed for variable interpolation), so `DB_PASSWORD` now has exactly one source of
  truth.
- [`.env.example`](.env.example) — updated the `DB_PASSWORD` comment to document this
  wiring and warn against hardcoding the value elsewhere.
- Production impact: production's `.env` already sets `DB_PASSWORD=diep123`
  (matching the previously-hardcoded value), so this change is a no-op for the running
  stack — `${DB_PASSWORD:-change-me-db-password}` resolves to `diep123` there, identical
  to before.

---

## F2 — Missing MQTT mTLS PKI artifacts (CRITICAL)

**Problem:** `mosquitto.conf` requires `mosquitto/config/certs/{ca,server}.{crt,key}`
and `mosquitto/config/passwd`; `dispatcher`/`ingestor`/`ev-charger` require
`certs/devices/{ca.crt,<id>.crt,<id>.key}`. None of these are tracked in git
(`.gitignore`), and no script generated them — `scripts/issue-device-cert.sh` explicitly
requires the CA to pre-exist ("run S3 first"), but no "S3" script existed. Result: on a
fresh clone, `diep-mqtt` exits immediately (`exit 13`, "Unable to open pwfile"), and
`dispatcher`/`ingestor`/`ev-charger` crash-loop with `FileNotFoundError` on `tls_set()`.

**Fix:** New script [`scripts/bootstrap-pki.sh`](scripts/bootstrap-pki.sh) (executable),
idempotent:
1. Generates the platform CA (`mosquitto/config/certs/ca.{crt,key}`).
2. Generates the broker server cert (`mosquitto/config/certs/server.{crt,key}`,
   CN=`diep-mqtt`, SANs `diep-mqtt`/`localhost`/`127.0.0.1`), signed by the CA.
3. Copies `ca.crt` into `certs/devices/`.
4. Runs `scripts/issue-device-cert.sh` for the full Installation Guide §6.1 fleet:
   `BAT001 EV001 INV001 MG001 METER001 ingestor dispatcher csms`.
5. Generates `mosquitto/config/passwd` (via `docker run ... eclipse-mosquitto
   mosquitto_passwd`) for the legacy password-auth identities `diep-device` and
   `diep-nodered` referenced by `mosquitto/config/acl`, using `MQTT_USER`/`MQTT_PASS`/
   `MQTT_NODERED_PASS` from `.env`.

Each step is skipped if its artifacts already exist, so re-running after adding new
device IDs only issues the new certs.

- [`.env.example`](.env.example) — added `MQTT_NODERED_PASS` (new var consumed by
  `bootstrap-pki.sh`).
- [`.gitignore`](.gitignore) — removed the dangling
  `!mosquitto/config/passwd.example` exception (no such template ever existed; the
  passwd file is now generated, not templated).
- [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md) §6.1 — rewritten from a
  narrative "generate a CA" description to a concrete `./scripts/bootstrap-pki.sh`
  step, run before the first `./start-all-diep.sh`.

---

## F3 — MQTT port exposure vs. documentation (MEDIUM)

**Problem:** Installation Guide §5.1 documents inbound `8883/tcp` for MQTT mTLS, but
`docker-compose.yml`'s `mqtt` service published `1883:1883` and `9001:9001` — both
listeners are commented out / retired in `mosquitto.conf` (mTLS-only on 8883). 8883 was
never published to the host, so even with valid certs (F2 fixed), no edge gateway could
reach the broker as documented.

**Fix:** [`docker-compose.yml`](docker-compose.yml) — `mqtt.ports` now publishes
`8883:8883` only; the dead `1883:1883`/`9001:9001` mappings are removed.
[`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md) §1 updated to reflect this
(previously an open "decide on legacy port mappings" item).

- Production impact: the running `diep-mqtt` container retains its old port mapping
  until recreated (`docker compose up -d mqtt`); this report does not restart it. Flagged
  as a follow-up for the production stack's next maintenance window.

---

## F4 — `devices.site_name` not seeded (MEDIUM)

**Problem:** `sql/001-004_seed_*.sql` inserted device rows without `site_name`, leaving
the FK column `NULL`. Site-scoped DERMS requests (`/derms/peak_shaving`,
`/derms/demand_response`, `/derms/battery_dispatch` with `"site_name": "..."`) 404 on a
fresh deploy ("No online battery available...", etc.) until an operator manually runs
`scripts/sql/site_name_backfill.sql` (the fix applied to production earlier today, per
[`SITE_NAME_BACKFILL_VALIDATION_REPORT.md`](SITE_NAME_BACKFILL_VALIDATION_REPORT.md)) —
an undocumented, non-repeatable step every fresh deploy would need to rediscover.

**Fix:**
- [`sql/000_schema.sql`](sql/000_schema.sql) — added a seed `INSERT INTO sites
  (site_name, site_type, latitude, longitude) VALUES ('Abuja Site A', 'microgrid',
  9.0765, 7.3986) ON CONFLICT (site_name) DO NOTHING;` immediately after the `sites`
  table/index are created, and before any `devices` rows are inserted (so the
  `devices_site_name_fkey` constraint is satisfiable from the first seed file onward).
- [`sql/001_commands.sql`](sql/001_commands.sql),
  [`sql/002_seed_battery_solar.sql`](sql/002_seed_battery_solar.sql),
  [`sql/003_seed_microgrid.sql`](sql/003_seed_microgrid.sql),
  [`sql/004_seed_smartmeter.sql`](sql/004_seed_smartmeter.sql) — every seed
  `INSERT INTO devices (...)` now includes `site_name = 'Abuja Site A'`.
- [`sql/003_seed_microgrid.sql`](sql/003_seed_microgrid.sql) — removed its now-redundant
  duplicate `sites` insert (superseded by the one in `000_schema.sql`), replaced with a
  comment pointing to it.

All inserts remain `ON CONFLICT ... DO NOTHING`, so `init-db.sh` (run via
`./start-all-diep.sh`) is still idempotent on an already-initialized database — this
change only affects the **initial** seed of a fresh database, it does not retroactively
modify production's `devices` table (already backfilled separately).

---

## F5 — Environment variable audit & documentation

**Audit method:** cross-referenced every `${VAR}` in `docker-compose.yml`, every
`os.environ`/`os.getenv` in `fastapi/`, `dispatcher/`, `ingestor/`, `portal/`, against
`.env.example`.

**Findings:**
- `DIEP_ACME_PASSWORD` and `DIEP_GLOBEX_PASSWORD` (per-tenant operator logins, Phase 12
  multi-tenancy demo) are read by `fastapi/auth.py` and explicitly named in Installation
  Guide §7's "rotate before go-live" list, but were **missing from `.env.example`**
  entirely (silently falling back to hardcoded `acme-2026`/`globex-2026`).
- `MQTT_NODERED_PASS` is a new var (added for F2's `bootstrap-pki.sh`) with no prior
  `.env.example` entry.
- All other compose-referenced and app-referenced vars (`DIEP_CORS_ORIGINS`,
  `DIEP_REFRESH_TTL`, `DIEP_BUILD`, etc.) have safe non-secret code-level defaults and
  are intentionally omitted from `.env.example` (operational tuning, not secrets).

**Fix:**
- [`.env.example`](.env.example) — added `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`
  (with `change-me-*` placeholders and a comment cross-referencing Guide §7), and
  `MQTT_NODERED_PASS`. `.env.example` is now 43 vars, all of which are either consumed
  directly by `docker-compose.yml` (`DB_*`, `REDIS_PASSWORD`, `MINIO_ROOT_*`) or by an
  application container via `env_file: .env`.
- [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md) §7 — pre-install checklist
  now says "review all N variables in `.env`" (N read from `.env.example` at doc-update
  time, currently 43) instead of naming only the original 5, explicitly calls out
  `DB_PASSWORD`'s dual role (F1), and adds the `bootstrap-pki.sh` step (F2) and a
  `/readyz` verification step.
- [`PILOT_RELEASE_CHECKLIST.md`](PILOT_RELEASE_CHECKLIST.md) §1 — pre-deployment secret
  rotation item expanded to the full credential list (`DB_PASSWORD`, `REDIS_PASSWORD`,
  `MINIO_ROOT_USER`/`PASSWORD`, `MQTT_PASS`/`MQTT_NODERED_PASS`, plus the original 5
  `DIEP_*` operator passwords), and the cert-generation item now points at
  `bootstrap-pki.sh`.

---

## Summary of files changed

| File | Change |
|---|---|
| `docker-compose.yml` | F1 (`timescaledb` env via `.env` substitution), F3 (`mqtt` ports → `8883:8883` only) |
| `.env.example` | F1 (comment), F2 (`MQTT_NODERED_PASS`), F5 (`DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`) |
| `.gitignore` | F2 (removed dangling `passwd.example` exception) |
| `scripts/bootstrap-pki.sh` | F2 (new file) |
| `sql/000_schema.sql`, `sql/001-004_seed_*.sql` | F4 (site seed + `devices.site_name`) |
| `DIEP_INSTALLATION_GUIDE.md` | F2, F5 (§6.1, §7 rewritten) |
| `PILOT_RELEASE_CHECKLIST.md` | F2, F3, F5 (§1 updated) |

## Not changed (out of scope for this remediation)

- Production's running containers/database — no restarts or migrations applied here.
- Operator-facing TLS (Guide §6.2, Caddy) — pre-existing known gap, unchanged.
- `diep-influxdb` (legacy, superseded by TimescaleDB) — flagged in
  `PILOT_RELEASE_CHECKLIST.md` as a pending decision, not removed.
- Alertmanager notification receiver — pre-existing known gap, unchanged.
