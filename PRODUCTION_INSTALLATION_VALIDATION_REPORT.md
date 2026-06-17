# DIEP Phase 20 — Production Installation Validation Report (Part A)

**Date:** 2026-06-17
**Validated against:** `PRODUCTION_INSTALLATION_VALIDATION_PLAN.md`
**Method:** Real execution — fresh `git clone` of `https://github.com/emmanoff-sys/diep-lab.git` into an isolated directory (`~/deploy-validation/phase20-fresh-install`), deployed as a separate Docker Compose project (`diep-phase20`), torn down at the end. No production modifications. No infrastructure changes to the existing pilot deployment.
**Result: CONDITIONAL — 5 of 10 pass/fail criteria fully pass, 1 partial, 4 require an undocumented workaround or fail as documented.**

---

## 1. Summary

A fresh install, executed by following only `DIEP_INSTALLATION_GUIDE.md`, reaches a working platform — but only after three undocumented, hands-discovered workarounds, one of which (Alertmanager) the install cannot complete without, and one of which (Grafana default credentials) is a real security gap. A fourth area (backups) "succeeds" by exit code while silently failing its actual job. This is exactly the class of problem that documentation review in Phases 17–19 could not have caught — it required literally running the install.

| Step | Result |
|---|---|
| 1. Fresh host simulation | PASS |
| 2. Clone from GitHub | PASS |
| 3. Follow installation guide only | PASS, with 1 documentation accuracy gap |
| 4. Generate PKI | PASS |
| 5. Deploy all services | PARTIAL — 23/24 containers healthy unattended; Alertmanager required an undocumented workaround |
| 6. Initialize database | PASS |
| 7. Validate monitoring | PASS, after the Alertmanager workaround; Grafana found wide open on default credentials |
| 8. Validate backups | FAIL as documented — scripts report success while the off-site upload silently fails |
| 9. Validate DERMS functionality | PARTIAL — full round-trip confirmed for EV charging only; the other 4 device verticals are not part of the default deployment |

---

## 2. Step-by-Step Results

### Step 1 — Fresh Host Simulation
Host: 4 vCPU, ~7.2 GiB RAM, ~48 GB disk — matches §1.1 pilot-sizing minimums. 9.1 GB of images already cached locally; ~20 GB free disk confirmed before deploying.

### Step 2 — Clone from GitHub
```
git clone https://github.com/emmanoff-sys/diep-lab.git
```
Completed in ~3 seconds, working tree 4.3 MB. No submodules, no errors.

### Step 3 — Follow Installation Guide Only
- Docker Engine and Compose V2 present — OK.
- `cp .env.example .env`, then all `change-me-*` defaults rotated to throwaway random values (verified zero `change-me` strings remained).
- **Finding (Documentation, Minor):** §7 instructs operators to "review all 40 variables" in `.env`. The actual `.env.example` contains 23 `KEY=value` lines. The instruction overstates the file's size; not load-bearing, but inaccurate.
- Host packages (`git`, `curl`, `jq`, `bc`, `openssl`, `cron`, `tar`, `python3`) — all present.

### Step 4 — Generate PKI
```
./scripts/bootstrap-pki.sh
```
Created CA, broker cert (CN=diep-mqtt), 8 device/service client certs, and `mosquitto/config/passwd`. Re-ran once — confirmed idempotent (no errors, no duplicate/overwritten artifacts).

### Step 5 — Deploy All Services
```
./start-all-diep.sh
```
`docker compose up -d` created and started all 24 defined services without error. `init-db.sh` ran and reported "Database initialization complete." The script's Node-RED readiness poll succeeded ("Node-RED is online"), and flow deployment to the running Node-RED instance succeeded (`deploy status: 204`).

**Finding (Blocker):** `diep-alertmanager` crash-looped indefinitely (`error loading configuration file: address ":": port cannot be empty`). Root cause: `alertmanager/alertmanager.yml.template` requires `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`, `ALERT_RECEIVER_EMAIL` — **none of which exist in `.env.example`, the installation guide, or any other document referenced by it.** A fresh install following the guide exactly ends with Alertmanager permanently down. Workaround applied for validation purposes only (placeholder values, not real secrets): added the five variables to `.env` and recreated the container, after which Alertmanager started cleanly. This is not optional configuration — without it, the container never reaches a running state.

**Finding (Minor, transient):** `diep-kafka-exporter` restarted 4 times in the first ~2 minutes after startup (`Tried to send a message to a replica that is not the leader for some partition`) while Kafka was still completing its own startup/leader election, then stabilized on its own. Not a blocker, but worth noting if a health-check / alerting system treats early restarts as a failure signal.

**Finding (Major):** `nodered/rebuild_flows.py` raised an unhandled `FileNotFoundError` on `/home/emmanuel/diep-lab/nodered/flows.json` — a developer-specific absolute path hardcoded into the script, unrelated to the actual install location. The flow deployment to the running Node-RED instance via its Admin API had already succeeded (confirmed independently: `GET /flows` on the fresh install returns 29 nodes matching the expected flow graph), so DERMS functionality is not impacted — but the script's intended side effect of writing a local backup copy of the flow definition back into the repo silently fails on every install whose directory layout doesn't match the original author's machine. `start-all-diep.sh` tolerates this failure (`|| true`), so it produces no visible error to the operator.

**Finding (Minor, Documentation):** The script's final service-URL printout lists Grafana, Prometheus, Alertmanager, cAdvisor, Node-RED, and Kafka UI — but omits the Portal (`:3002`) and FastAPI (`:8000`) endpoints, despite both being deployed.

**Finding (Architecture/Documentation, Minor):** Every service in `docker-compose.yml` uses an explicit `container_name:` (e.g. `diep-mqtt`, `diep-portal`) rather than the Compose-default project-prefixed name. This was confirmed directly: pre-existing exited containers from the main `diep-lab` project on this host carry the exact same names this fresh install needed. Two DIEP environments cannot run side-by-side on the same host — a second `docker compose up -d` will fail with "name already in use" if the first environment's containers are running. `COMPOSE_PROJECT_NAME` alone (as used for this validation) only isolates the network/volumes, not the containers, and only worked here because the original project's containers happened to be stopped.

**Minor count discrepancy:** Installation guide describes "25 containers"; `docker-compose.yml` defines 24 services (excluding 7 volumes + 1 network). Not blocking.

### Step 6 — Initialize Database
Verified directly against the running TimescaleDB:
- 14 tables present (`devices`, `telemetry`, `commands`, `audit_events`, `derms_requests`, etc.)
- 1 hypertable (`telemetry`)
- 5 background jobs present: 2 continuous-aggregate refreshes (`telemetry_1m`, `telemetry_1h`), compression policy, and 2 retention policies — all created by the documented `init-db.sh` with no manual SQL.

**PASS** — matches the Phase 9 schema baseline with zero undocumented steps.

### Step 7 — Validate Monitoring
After the Alertmanager workaround above:
- Prometheus: all 6 configured targets (`cadvisor`, `diep-fastapi`, `kafka-exporter`, `node-exporter`, `postgres-exporter`, `prometheus`) report `up`.
- Grafana: `/api/health` reports `database: ok`; 3 provisioned dashboards present (DIEP Command/Control Plane, DIEP Kafka, DIEP PostgreSQL/TimescaleDB).
- Alertmanager: reachable, cluster status `ready`, configuration loaded (post-workaround).

**Finding (Blocker, Security):** Grafana accepted the **default `admin`/`admin` credentials** with full API access. `docker-compose.yml`'s `grafana` service sets no `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`, and no Grafana-specific variable exists anywhere in `.env.example`. Every operator who rotates the 13 documented `change-me-*` values (as Step 3 instructs) still ends up with a Grafana instance — exposed per §5's own port table on `:3001` — reachable with the tool's well-known default credentials. This is a distinct gap from the SEC-1→5 items already tracked in `PRODUCTION_DEPLOYMENT_TRACKER.md` (which cover DIEP-issued credentials, not Grafana's own).

### Step 8 — Validate Backups
```
./scripts/backup-db.sh
./scripts/backup-config.sh
./scripts/verify-backup.sh
./scripts/install-backup-cron.sh
```

**Finding (Blocker):** Both `backup-db.sh` and `backup-config.sh` reported `EXIT=0` ("Backup complete") while the MinIO off-site upload step silently failed:
```
mc: <ERROR> Unable to initialize new alias from the provided credentials.
Get "http://diep-minio:9000/...": dial tcp: lookup diep-minio on 127.0.0.11:53: server misbehaving.
```
Root-caused to two compounding issues in both scripts:
1. `DIEP_NET` defaults to the literal string `diep-lab_diep-net` (line: `NET="${DIEP_NET:-diep-lab_diep-net}"`). This only resolves correctly if the clone directory and Compose project name happen to be exactly `diep-lab`. Any other directory name, or any explicit `COMPOSE_PROJECT_NAME` override (as this validation used), breaks DNS resolution of `diep-minio` from the ephemeral `minio/mc` container the script launches.
2. The MinIO upload block ends in a bare `|| true` applied, by shell operator precedence, to the **entire `&&`-chained command sequence** — not just the final prune step it was clearly intended to make non-fatal. As a result, *any* failure in the upload chain (wrong network, wrong credentials, MinIO down, full disk) is swallowed, and the script always reports success.

Confirmed root cause by re-running with the correct values exported (`DIEP_NET=diep-phase20_diep-net`, real rotated `MINIO_ROOT_USER`/`PASSWORD`) — the upload then succeeded and objects appeared in the bucket. **A scheduled nightly cron-driven backup on a production install named anything other than exactly `diep-lab` would silently never reach off-site storage, and nothing in the exit code, logs, or a naive "did the cron job succeed" check would reveal it.** This is a serious, validated finding — not a documentation gap, a logic bug with production safety implications.

`verify-backup.sh` — **PASS**. Performed a real restore-into-scratch-database drill and compared row counts against the live database; completed in 4 seconds with no manual intervention.

`install-backup-cron.sh` — **PASS** as documented: confirmed idempotent (re-running produces no duplicate crontab entries) and installs exactly the 3 documented schedule lines.

**Process note (not a DIEP defect):** While testing `install-backup-cron.sh` in the isolated clone, the validator did not first inspect pre-existing crontab content. The script's own logic (by design) removes any prior `# diep-backup`-tagged lines before adding new ones, and a subsequent cleanup step removed all such lines — which turned out to include a **pre-existing, legitimate cron entry for the main `diep-lab` project** (confirmed via `syslog`: last real execution 2026-06-15 02:30). This was caught immediately, disclosed to the user, and restored exactly (the script is deterministic, and the restored entries were verified byte-for-byte against the syslog evidence of the original). No data loss occurred — backups for 2026-06-05 and 2026-06-13 remained intact in the main project's `backups/` directory throughout. Listed here for completeness/transparency, not as a finding against the codebase.

### Step 9 — Validate DERMS Functionality
- `/readyz` → `{"ready": true, "checks": {"database": true, "redis": true}}` — **PASS**.
- **Finding (Major/Documentation):** Of the 5 device verticals named in the validation scope (EV charging, solar curtailment, battery control, smart meter, microgrid), only the EV charger (`ev-charger` service) is enabled by default in `docker-compose.yml`. The other four (`battery`, `solar`, `microgrid`, `smartmeter`) are tagged `profiles: ["legacy-disabled"]` and are not started by `docker compose up -d` / `start-all-diep.sh`. Compose comments indicate they are "superseded by `docker-compose-battery-edge.yml`" and similar edge-specific files — none of which are referenced anywhere in `DIEP_INSTALLATION_GUIDE.md`. An operator following the guide alone cannot exercise 4 of the 5 documented DERMS command types.
- **EV charging round-trip — confirmed end-to-end, live:**
  1. `POST /commands` (operator-scoped API key) with `{"device_id":"EV001","command_type":"start_charging","params":{"power_limit_kw":11.0}}` → `202`-equivalent, `status: SENT`, dispatched to Kafka topic `diep.commands`.
  2. Dispatcher relayed to MQTT (mTLS) → EV001 simulator received and executed it (`charging: True`, `power_kw` ramped to 12.97), published an ack.
  3. Dispatcher consumed the ack; `GET /commands/{id}` showed `status: ACKED` with `dispatched_at` and `acked_at` timestamps roughly 1 second apart.
- **mTLS enforcement — confirmed via broker logs**, not just inference: a TLS connection attempt to `:8883` presenting no client certificate was rejected by Mosquitto (`OpenSSL Error ... peer did not return a certificate` → `disconnected: Protocol error`), while the real EV001 simulator, ingestor, and dispatcher all connected successfully with their issued certificates (`negotiated TLSv1.3 cipher TLS_AES_256_GCM_SHA384`).

---

## 3. Pass/Fail Criteria Results

| # | Criterion | Result |
|---|---|---|
| 1 | Clean clone | **PASS** |
| 2 | PKI bootstrap + idempotency | **PASS** |
| 3 | Service deployment | **PARTIAL** — 23/24 healthy unattended; Alertmanager required an undocumented `.env` workaround to reach a running state |
| 4 | Database initialization | **PASS** |
| 5 | `/readyz` | **PASS** |
| 6 | Monitoring | **PARTIAL** — Prometheus/Grafana/Alertmanager all reachable post-workaround; Grafana found reachable on default `admin/admin` |
| 7 | Backups | **FAIL** — both backup scripts report success while silently failing the off-site upload (network-name default + masking `\|\| true` bug) |
| 8 | DERMS round-trip | **PARTIAL** — full round-trip confirmed for 1 of 5 documented device verticals; the other 4 are excluded from the default deployment, undocumented |
| 9 | mTLS enforcement | **PASS** (confirmed via broker logs, both negative and positive cases) |
| 10 | Documentation completeness | **FAIL** — 3 separate undocumented requirements found (Alertmanager SMTP vars, Grafana admin credential, backup network/credential exports), plus the device-vertical scope gap |

**Overall: CONDITIONAL.** 5 PASS, 3 PARTIAL, 2 FAIL. Per the plan's rule, Overall PASS requires all 10 — not met. None of the failures are cosmetic; two (Grafana default credentials, silently-failing backups) are production-safety issues independent of anything already tracked in `PRODUCTION_DEPLOYMENT_TRACKER.md`.

---

## 4. New Issues Discovered (not previously tracked anywhere)

| ID | Severity | Issue | Evidence |
|---|---|---|---|
| INSTALL-1 | Blocker | Alertmanager cannot start without 5 undocumented `ALERT_SMTP_*`/`ALERT_RECEIVER_EMAIL` env vars | Crash loop logs; fixed by adding vars + recreate |
| INSTALL-2 | Blocker (Security) | Grafana reachable with default `admin`/`admin`; no `GF_SECURITY_ADMIN_PASSWORD` wired anywhere | `curl -u admin:admin .../api/search` → 200 |
| INSTALL-3 | Blocker | `backup-db.sh` / `backup-config.sh` report success while silently failing MinIO upload (wrong `DIEP_NET` default + misplaced `\|\| true`) | Reproduced; root-caused; fixed by exporting correct values |
| INSTALL-4 | Major | `rebuild_flows.py` hardcodes `/home/emmanuel/diep-lab/...`; crashes on every install with a different path (flows still deploy via API, but local backup copy is never written) | Traceback in install log |
| INSTALL-5 | Major | Only 1 of 5 documented DERMS device types is enabled by default; the other 4 require undocumented edge compose files | `profiles: ["legacy-disabled"]` in `docker-compose.yml` |
| INSTALL-6 | Minor | `container_name:` hardcoded for every service — two DIEP environments cannot coexist on one host | Confirmed via identical pre-existing container names |
| INSTALL-7 | Minor (transient) | `kafka-exporter` restarts ~4x during Kafka startup before stabilizing | Container logs, restart count |
| INSTALL-8 | Minor (Documentation) | Guide says "review all 40 variables"; `.env.example` has 23 | `grep -c` |
| INSTALL-9 | Minor (Documentation) | `start-all-diep.sh` URL printout omits Portal (:3002) and FastAPI (:8000) | Script output |
| INSTALL-10 | Minor (Documentation) | Guide says "25 containers"; compose defines 24 services | `grep` count |

---

## 5. Installation Time

| Phase | Duration |
|---|---|
| `git clone` | ~3 seconds |
| Prerequisite checks, `.env` setup/rotation, PKI bootstrap (incl. idempotency re-run) | a few minutes (manual/interactive, not separately timed) |
| `docker compose up -d` (24 containers) | ~14 seconds to all-Started |
| `init-db.sh` + Node-RED readiness wait + flow deploy | additional 1–3 minutes |
| **Total wall-clock, clone to fully running platform** | **approximately 18–20 minutes**, including the Alertmanager workaround |

No GPU/large-model downloads were needed; 9.1 GB of images were already cached on this host, which materially shortens this number versus a true offline-to-online first pull.

---

## 6. Security Observations Carried Forward

- `DIEP_PORTAL_TOKEN` in `.env.example` defaults to literally the same value as `DIEP_ADMIN_KEY` — i.e. it is not an independently-scoped secret. Not a new finding, but worth flagging alongside INSTALL-2 above as part of the same "default credential hygiene" theme.
- All credential rotation performed during this validation used `secrets.token_urlsafe`/`secrets.token_hex`-generated throwaway values. No real `.env` values from the existing pilot deployment were read, reproduced, or logged at any point in this validation.

---

**Report prepared by:** DIEP Platform Engineering — Phase 20 Validation
**Environment:** isolated, torn down after validation (see Part C teardown)
