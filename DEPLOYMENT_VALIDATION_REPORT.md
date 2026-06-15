# DIEP `v1.0.0-pilot` — Independent Deployment Validation Report

**Date:** 2026-06-15
**Role:** Independent deployment engineer, no prior tribal knowledge assumed.
**Source:** `git@github.com:emmanoff-sys/diep-lab.git`, tag `v1.0.0-pilot`
(commit `2da22f9`), `DIEP_INSTALLATION_GUIDE.md`, `DIEP_OPERATIONS_MANUAL.md`.
**Workspace:** `/home/emmanoff_lab/deploy-validation/diep-lab-pilot/` — a
fresh `git clone` + `git checkout v1.0.0-pilot`, entirely separate from the
running production stack at `/home/emmanoff_lab/projects/diep-lab/`.
**Production impact:** None. The production `diep-lab` stack (containers
`diep-*`) was running throughout and was not stopped, restarted, or
reconfigured. The validation stack used a different Compose project name
(`diep-pilot-val`), renamed containers (`val-diep-*`) and remapped host
ports (+10000) purely so it could run side-by-side on this shared host —
**this remapping is not part of the published docs**; a real fresh-host
deploy would use the documented ports as-is. The validation stack was fully
torn down (`docker compose down` + volumes removed) at the end of this
exercise; production was confirmed still running and unaffected.

---

## 1. What the documentation actually is

`DIEP_INSTALLATION_GUIDE.md` is explicitly a **requirements/checklist
document**, not a step-by-step procedure:

> "This guide documents requirements only — no installation steps were
> executed against any new environment as part of producing it."

The only executable step it points to is item 8 of its pre-install
checklist: run `./start-all-diep.sh` (defined and explained in
`DIEP_OPERATIONS_MANUAL.md` §1.1). Everything else in the guide is
hardware/OS/network/certificate **requirements**, not actions. A
first-time installer following "the installation guide" literally has
exactly one command to run (`./start-all-diep.sh`), preceded by an
unordered checklist that includes several items with no accompanying
how-to (see §3 below).

---

## 2. Step-by-step walkthrough performed

| # | Step (as documented) | Outcome |
|---|---|---|
| 1 | Provision host per §1-3 (4 vCPU/8 GiB/100 GB, Ubuntu 22.04/24.04, Docker ≥24, `docker` group) | Used existing lab host (already meets spec); not independently re-provisioned. |
| 2 | `git clone` + `git checkout v1.0.0-pilot` | **OK.** Tag resolves to commit `2da22f9` (same as `main` — single-commit baseline tag). |
| 3 | Populate `.env` from `.env.example`, "rotate all secrets" | `.env.example` present, well-commented, **40 vars**. For this validation we used `cp .env.example .env` unmodified (as the comment says, "the code ships with lab DEFAULTS so the stack runs out of the box"). **Finding F1** (below) is a direct consequence of these defaults not being internally consistent. |
| 4 | Generate/place mTLS CA + per-device certs under `certs/devices/` and `mosquitto/config/certs/` (§6.1) | **Blocked — Finding F2.** No CA exists, no script to create one, and the directories don't exist in a fresh clone. |
| 5 | Update `mosquitto/config/acl` for the device fleet | File exists and is populated for the lab's 5 devices + services; usable as a template, but step 4 blocks the broker regardless. |
| 6 | Configure TLS reverse proxy for Portal/Grafana/API (§6.2) | Not attempted — explicitly marked "not yet enabled in the lab" by the guide itself; out of scope for functional validation (HTTP-only is the documented current state). |
| 7 | Run `./start-all-diep.sh` (§7 checklist item, detailed in Ops Manual §1.1) | Ran the equivalent (`docker compose up -d` + `init-db.sh` schema/seed). **24/24 containers created, 19/20 long-running services reached `Up`**, `diep-mqtt` crash-loops (Finding F2). |
| 8 | Post-startup verification: `curl /healthz`, `curl /readyz`, `docker compose ps` | `/healthz` → `200 {"status":"ok"}`. `/readyz` → **`{"ready": false, "checks": {"database": false, "redis": true}}`** out of the box — **Finding F1**. |
| 9 | Install backup cron (`scripts/install-backup-cron.sh`) | Script present and executable; not run (would install a crontab on the shared host — out of scope/destructive to host config, correctly so per "do not modify the running production environment"). |
| 10 | Run UAT plan (`DIEP_UAT_TEST_PLAN.md`) | Not run in full; targeted functional checks below substitute for it. |

---

## 3. Findings

### F1 — CRITICAL: `.env.example` default `DB_PASSWORD` does not match the database password the stack actually creates

- `docker-compose.yml` (`timescaledb` service) hardcodes:
  ```yaml
  environment:
    POSTGRES_DB: diep
    POSTGRES_USER: diep
    POSTGRES_PASSWORD: diep123
  ```
  This is **not** parameterized by `.env` — TimescaleDB's `POSTGRES_PASSWORD`
  is always `diep123` regardless of `.env` contents.
- `.env.example` sets:
  ```
  DB_PASSWORD=change-me-db-password            # was hardcoded 'diep123'
  ```
  The comment ("was hardcoded") signals an intended migration that was
  **never completed** in `docker-compose.yml`. `fastapi`, `dispatcher`, and
  `ingestor` all read `DB_PASSWORD` from `.env` via `env_file: .env`.
- **Observed effect (live test):** following the guide exactly
  (`cp .env.example .env`, `docker compose up -d`, `init-db.sh`) produces a
  stack where TimescaleDB's actual password is `diep123` but FastAPI tries
  `change-me-db-password`. Result: `GET /readyz` →
  `{"ready": false, "checks": {"database": false, "redis": true}}`
  **permanently** — every API client that checks readiness before sending
  traffic (load balancers, the Portal, the dispatcher's own DB writes, the
  UAT plan's first gate) sees the platform as not ready, indefinitely,
  with **zero indication of why** (FastAPI logs show no error — the
  connection attempts simply never succeed silently until checked).
- **Verified fix (in the disposable validation environment only):**
  `ALTER USER diep WITH PASSWORD 'change-me-db-password';` inside
  TimescaleDB, then `docker restart fastapi` → `/readyz` →
  `{"ready": true, "checks": {"database": true, "redis": true}}`.
  This confirms the mismatch is the sole cause.
- **Not documented anywhere**: neither the Installation Guide's pre-install
  checklist nor the Operations Manual's post-startup verification (§1.3)
  mentions this, and §1.3 even states the *expected* (passing) `/readyz`
  response as if it's the normal out-of-the-box result.

### F2 — CRITICAL: MQTT mTLS material referenced by the docs does not exist in the repo, and no generation procedure is documented or scripted

Three layers of missing artifacts, discovered by actually starting the
stack:

1. **`mosquitto/config/passwd`** — referenced by `mosquitto.conf`
   (`password_file /mosquitto/config/passwd`). `.gitignore` has an
   exception `!mosquitto/config/passwd.example` implying a template should
   exist, but **no `passwd` or `passwd.example` file is present** in
   `mosquitto/config/` at all. Mosquitto's first log line on a fresh clone
   is:
   ```
   password-file: Error: Unable to open pwfile "/mosquitto/config/passwd".
   mosquitto version 2.1.2 terminating
   ```
   → `diep-mqtt` crash-loops (`exit 13`) immediately, before TLS is even
   evaluated.

2. **`mosquitto/config/certs/{ca.crt,ca.key,server.crt,server.key}`** —
   required by `mosquitto.conf`'s `listener 8883` block (the *only* active
   listener per Phase 9J-S4). **Entirely absent** — `certs/` and
   `mosquitto/config/certs/` are `.gitignore`d and were never populated by
   this tag. `scripts/issue-device-cert.sh` (the only cert-related script
   in the repo) explicitly requires this CA to **already exist** ("CA not
   found in mosquitto/config/certs (run S3 first)") — but **there is no
   "S3" script in the repo**, and no doc describes how to generate the CA
   and server cert from scratch. `RELEASE_CERTIFICATION_REPORT.md` /
   `GIT_SANITIZATION_INVENTORY.md` (internal, not part of the published
   install docs) confirm the lab's CA key was deliberately excluded from
   Git and that "a fresh CA must be regenerated for any pilot or production
   deployment" — but give no procedure either.

3. **`certs/devices/{BAT001,EV001,INV001,MG001,METER001,ingestor,dispatcher,csms}.{crt,key}`**
   — bind-mounted read-only into `ingestor`, `dispatcher`, and every device
   simulator (`./certs/devices:/certs:ro`). Also entirely absent.
   `issue-device-cert.sh` *could* generate these, but only after #2 exists.

- **Observed effect (live test):**
  - `diep-mqtt`: `Restarting (13)` — crash loop, 9 restarts in ~12 minutes.
  - `diep-dispatcher`, `diep-ingestor`, `diep-ev-charger` (the one device
    simulator enabled by default): each crashes on startup with
    `FileNotFoundError: [Errno 2] No such file or directory` from
    `paho.mqtt.client.tls_set()`, and restart-loops (3-5 restarts observed
    in ~2 minutes). `docker-compose.yml` itself documents that the *other*
    four device simulators (smartmeter/battery/solar/microgrid) are
    **disabled by default specifically "to avoid a ConnectionRefusedError
    crash loop"** — i.e., the same root cause is already known to make 4 of
    5 simulators unusable out of the box, and is simply hidden by not
    starting them.
  - **End-to-end consequence**: a DERMS command (`POST
    /derms/battery_dispatch`) is accepted by FastAPI, written to
    `derms_requests` as `EXECUTED`, and published to Kafka — but the
    corresponding row in `commands` stays `status=SENT` forever, because
    `diep-dispatcher` (which would publish it to MQTT and record the device
    ACK) never successfully starts. From an operator's perspective via the
    API, the command "succeeded" but the device never received it, with no
    error surfaced.

- **Fix is well-understood but entirely undocumented for a fresh deploy**:
  generate a CA + server cert (openssl, ~10 lines, same pattern as
  `issue-device-cert.sh`), place under `mosquitto/config/certs/`, create
  `mosquitto/config/passwd` (`mosquitto_passwd`), then run
  `scripts/issue-device-cert.sh <id>` for each of `BAT001`, `EV001`,
  `INV001`, `MG001`, `METER001`, `ingestor`, `dispatcher`, `csms`. None of
  this is in `DIEP_INSTALLATION_GUIDE.md`'s pre-install checklist as an
  actionable step (§6.1 describes it narratively as "for a customer pilot:
  1. Generate (or extend) the CA..." but with no commands, no script
  reference, and it's not in the §7 checklist).

### F3 — MEDIUM: Installation Guide's documented inbound port for MQTT (8883) is not published by `docker-compose.yml`

- `DIEP_INSTALLATION_GUIDE.md` §5.1 lists **8883/tcp (mTLS)** as the port
  "Site edge gateways" must reach on the pilot host.
- `mosquitto.conf`'s only active listener is **8883**.
- `docker-compose.yml`'s `mqtt` service publishes **`1883:1883`** and
  `9001:9001`** to the host — both listeners are commented out
  ("RETIRED") in `mosquitto.conf`, so these published ports correspond to
  **nothing actually listening**. **8883 is never published to the host at
  all.**
- Net effect: even after fixing F2, an external edge gateway following
  §5.1 (open 8883 to the host) would connect to a port the container never
  exposes — only containers on `diep-net` (e.g. `dispatcher`, `ingestor`,
  on the same Docker network) can reach 8883 via the internal alias
  `diep-mqtt:8883`. This is fine for the lab's all-in-one-host topology but
  contradicts the "Site edge gateways" inbound requirement in §5.1, which
  implies external (off-host) reachability.

### F4 — MEDIUM: `devices.site_name` is unpopulated by the documented seed data, breaking site-scoped DERMS calls out of the box

- `init-db.sh` runs `sql/000_schema.sql` through `sql/011_tenancy.sql`.
  After this, all 5 seeded devices have `site_name IS NULL` even though the
  `sites` table is seeded with exactly one row (`Abuja Site A`) and every
  device's `location` already says `Abuja Site A`.
- `POST /derms/peak_shaving` (and `demand_response`,
  `battery_dispatch`) with `{"site_name": "Abuja Site A", ...}` —
  the form shown as the canonical example in `DERMS_VALIDATION_REPORT.md`
  and exercised by the UAT plan — returns `404 "No online battery available
  to support peak shaving"` on a freshly-seeded database, because
  `_select_device()` filters on `site_name = %s` and no device has one.
  (Device-ID-scoped calls, e.g. `{"device_id":"BAT001", ...}`, work
  correctly.)
- This is the same gap independently identified and fixed for the running
  production database in `SITE_NAME_AUDIT_REPORT.md` /
  `SITE_NAME_BACKFILL_VALIDATION_REPORT.md` (2026-06-15), but **that fix
  (`scripts/sql/site_name_backfill.sql`) is not part of `init-db.sh` /
  the documented install sequence**, so every fresh deploy reproduces the
  gap until someone reruns that ad-hoc backfill.

### F5 — LOW: Ambiguous/incomplete pre-install checklist items

- §7 checklist item "`.env` populated from `.env.example` with **all**
  secrets rotated" lists 5 specific passwords to rotate
  (`DIEP_ADMIN_PASSWORD`/`DIEP_OPERATOR_PASSWORD`/`DIEP_VIEWER_PASSWORD`/
  `DIEP_ACME_PASSWORD`/`DIEP_GLOBEX_PASSWORD`) but `.env.example` actually
  contains **40 variables**, most of which are also `change-me-*` defaults
  (`DB_PASSWORD`, `REDIS_PASSWORD`, `MINIO_ROOT_PASSWORD`,
  `DIEP_JWT_SECRET`, `DIEP_SERVICE_TOKEN`, `DIEP_OPERATOR_KEY`,
  `DIEP_ADMIN_KEY`, `MQTT_PASS`, etc.). The checklist's "all secrets" claim
  and its 5-item enumeration are inconsistent — a first-time installer
  copying `.env.example` to `.env` and rotating only the 5 named items
  would still ship 35+ default credentials.
- §6.1 step 3 ("Update `mosquitto/config/acl`...") and step 4
  ("Certificate rotation... not currently automated") are narrative
  guidance, not procedures — no example `acl` syntax, no rotation script
  reference.
- The Operations Manual's "expected" `/readyz` response (§1.3) is presented
  without caveats, which (given F1) is actively misleading for a first-time
  installer — they have no signal that `database: false` is a *known*
  out-of-the-box state requiring a fix, vs. a sign their own environment is
  broken.

---

## 4. Component validation results

Validation was performed against the side-by-side `diep-pilot-val` stack
(remapped ports, see header). For F1, the DB password was corrected
**in the disposable validation environment only** to isolate and confirm
the root cause; all other results below reflect the stack exactly as
produced by `cp .env.example .env && docker compose up -d && init-db.sh`.

| Component | Result | Evidence |
|---|---|---|
| **Docker stack startup** | **Partial.** 24/24 containers created. 19 long-running services reach `Up`/`Up (healthy)` and stay up. `diep-mqtt` crash-loops (F2). 4/5 device simulators are disabled by default for the same reason (documented in-file as a workaround, not in the install docs). | `docker compose -p diep-pilot-val ps -a` |
| **TimescaleDB** | **Works.** Container healthy, `pg_isready` OK. `init-db.sh`'s 12 SQL files apply cleanly and **idempotently** (re-run produced zero errors). 5 devices + sites + tenants seeded correctly. | `psql` output, schema re-apply test |
| **Redis** | **Works.** `requirepass` enforced; `.env.example`'s default `REDIS_PASSWORD` authenticates (`PONG`). | `redis-cli -a ... ping` |
| **MQTT (Mosquitto)** | **Fails — does not start.** Crash loop, `exit 13`, missing `passwd` file before TLS certs are even reached (F2). | `docker logs val-diep-mqtt` |
| **Kafka** | **Works**, with a slow first-boot. KRaft single-node broker took ~2 minutes to settle (`BrokerLifecycleManager` heartbeat timeouts during initial metadata bootstrap, not seen on the long-running production broker); after that, `kafka-broker-api-versions.sh` and topic operations responded normally (`isFenced: false`). Not blocking, but worth noting in a "how long until healthy" expectation — not documented anywhere. | `docker logs val-diep-kafka`, `kafka-broker-api-versions.sh` |
| **FastAPI** | **Starts, but reports not-ready out of the box** (F1). `/healthz` = 200 always. `/readyz` = `{"ready": false, "checks": {"database": false, "redis": true}}` until the DB-password mismatch is corrected; `{"ready": true, ...}` afterward. | `curl /healthz`, `/readyz` before/after |
| **Portal** | **Works** (after ~10s Next.js dev-server compile on first request — `Compiling /` then 200). No functional issue, but the guide gives no expectation-setting for first-hit latency. | `curl -o /dev/null -w "%{http_code}"` → 200 |
| **Monitoring** (Prometheus, Alertmanager, Grafana, cAdvisor, node-exporter, postgres-exporter, kafka-exporter, kafka-ui) | **All 8 healthy / 200 OK** out of the box. | `curl` against each `/healthy`, `/api/health`, `/metrics`, etc. |
| **DERMS** | **Partially works.** `POST /derms/battery_dispatch` with `device_id=BAT001` (auth via `.env.example` default operator credentials) returns 200, creates a `derms_requests` row (`status=EXECUTED`) and a `commands` row. **However**: (a) the command row stays `status=SENT` forever — never `ACKED` — because `diep-dispatcher` cannot start (F2); (b) the same request scoped by `site_name` instead of `device_id` returns `404` because of F4. | `curl /derms/battery_dispatch`, `derms_requests`/`commands` table queries, dispatcher logs |

---

## 5. Readiness scores

### 5.1 Documentation Readiness Score: **2.5 / 5**

The Installation Guide is thorough on *requirements* (hardware/OS/network/
cert specs are detailed and accurate against the live stack) but provides
**no executable installation procedure** beyond "run
`./start-all-diep.sh`", and is silent on — or actively contradicts — three
things a fresh install needs: (1) how to generate the MQTT mTLS CA/certs
it requires (§6.1 is narrative only, references no script, and the one
script that exists assumes the CA already exists); (2) the DB-password
mismatch between `.env.example` and `docker-compose.yml` that makes
`/readyz` fail forever; (3) the `site_name` backfill needed for the
documented DERMS request shape. The pre-install checklist's "rotate all
secrets" item undercounts the actual 40-variable `.env.example` by 8x.

### 5.2 Deployment Readiness Score: **2 / 5**

`git clone` + checkout + `cp .env.example .env` + `docker compose up -d` +
`init-db.sh` gets you 19 of 24 containers healthy, a working data plane
(TimescaleDB/Redis/Kafka), a working API surface and Portal, and a fully
working monitoring stack — entirely from the published artifacts, with no
edits required to get *that* far. But the platform's core purpose
(telemetry ingestion + command dispatch to devices over MQTT, and
readiness-gated API traffic) is **non-functional out of the box** due to
F1 (DB password mismatch — every readiness check fails) and F2 (no MQTT
broker — ingestor/dispatcher/all simulators crash-loop). Both are fixable
in minutes by someone who already knows the codebase, but **neither fix is
documented**, and F1 in particular fails *silently* from the installer's
perspective (no error, just a perpetual `"ready": false`).

### 5.3 Overall Platform Readiness Score: **2.5 / 5**

The platform *design* and the *running production instance* (validated
extensively in other reports in this repo — `DERMS_VALIDATION_REPORT.md`,
`DATABASE_VALIDATION_REPORT.md`, `KAFKA_REDIS_FIX_VALIDATION_REPORT.md`,
etc.) are solid: once correctly configured, every subsystem checked here
(TimescaleDB, Redis, Kafka, FastAPI, Portal, monitoring, DERMS) works
correctly and the architecture is coherent. But "deployed from scratch
using only the published documentation" — the literal scope of this
exercise — currently **does not produce a working pilot**: an installer
with no tribal knowledge would end up with a stack that *looks* up
(`docker compose ps` shows mostly "Up") but is non-functional for its
primary use cases (telemetry, command dispatch, readiness-gated traffic,
site-scoped DERMS), with no error messages pointing at the actual causes.
This tag is **not yet pilot-deployable by an independent operator without
direct support from the development team**.

---

## 6. Recommended remediation (priority order)

1. **F1**: Either parameterize `docker-compose.yml`'s `timescaledb.environment.POSTGRES_PASSWORD` as `${DB_PASSWORD}` (recommended — makes `.env` the single source of truth), or change `.env.example`'s `DB_PASSWORD` default to `diep123` and document that it must be rotated *consistently in both places* if changed. Add a CI/smoke check that asserts `/readyz` returns `ready: true` on a fresh `docker compose up`.
2. **F2**: Add a script (e.g. `scripts/init-mtls-ca.sh`) that generates the CA, server cert/key under `mosquitto/config/certs/`, and a default `mosquitto/config/passwd`, then loops `scripts/issue-device-cert.sh` over the standard device/service IDs. Reference it explicitly as a numbered step in the Installation Guide §7 checklist, before "Run `./start-all-diep.sh`".
3. **F4**: Fold `scripts/sql/site_name_backfill.sql` (or equivalent `UPDATE`) into `sql/002_seed_battery_solar.sql`/`003_seed_microgrid.sql`/`004_seed_smartmeter.sql` (or a new `sql/012_site_assignment.sql`) so `init-db.sh` produces devices with `site_name` populated.
4. **F3**: Either publish `8883:8883` on the `mqtt` service in `docker-compose.yml`, or correct §5.1 of the Installation Guide to clarify that 8883 is `diep-net`-internal only in this single-host topology and edge-gateway connectivity requires an additional reverse-proxy/TLS-passthrough layer not yet implemented.
5. **F5**: Reconcile the §7 "rotate all secrets" checklist item with the actual 40-variable `.env.example` (either enumerate all of them or reference `.env.example` directly as "rotate every `change-me-*` value").
