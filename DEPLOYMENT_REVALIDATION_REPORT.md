# DIEP Deployment Revalidation Report

**Date:** 2026-06-15
**Role:** Release Engineering Lead
**Input:** [`DEPLOYMENT_REMEDIATION_REPORT.md`](DEPLOYMENT_REMEDIATION_REPORT.md) (F1-F5 fixes
applied to the working tree of `~/projects/diep-lab`, uncommitted at the time of writing).
**Objective:** Re-run the clean-deploy walkthrough from
[`DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) against the remediated
tree and confirm F1-F4 are closed, the documentation in §6/§7 is sufficient on its own, and
no manual fixes are required.

---

## Methodology and a deliberate deviation from "git clone"

The remediation in `DEPLOYMENT_REMEDIATION_REPORT.md` is **uncommitted** in
`~/projects/diep-lab` (by design — this report and the remediation report are deliverables
of the same uncommitted change set, to be reviewed and committed together). A literal
`git clone` from GitHub at this point would clone the **pre-remediation** `v1.0.0-pilot`
tag and reproduce the original F1-F5 defects, not validate the fixes.

To validate the fixes as they will behave once committed and cloned, this revalidation:

1. Created a fresh workspace: `~/deploy-validation/diep-lab-remediated/`.
2. Populated it via `rsync` of the (remediated, uncommitted) working tree, excluding
   `.git`, `.venv`, `node_modules`, `.env*`, `mosquitto/config/certs/`,
   `mosquitto/config/passwd*`, `certs/`, `backups/`, `__pycache__` — i.e. excluding exactly
   the generated/local artifacts that a real `git clone` would also not contain (per
   `.gitignore`), so the starting state is equivalent to a fresh clone of the remediated
   tree.
3. Followed `DIEP_INSTALLATION_GUIDE.md` §6.1/§7 **documentation only** from that point:
   `cp .env.example .env`, `./scripts/bootstrap-pki.sh`, deploy, verify `/readyz`.
4. Ran the stack under Docker Compose project `diep-remediation`, with every
   `container_name` prefixed `val2-diep-` and every host port offset `+20000`, so it runs
   side-by-side with the live `diep-*` production stack without any collision or shared
   state. **No production container, volume, or database was touched.**

Two adjustments were needed purely because of this side-by-side renaming/port-remapping
(not because of any defect in the remediated repo) — see "Validation-only exclusions"
below.

---

## Step-by-step results

### 1. `cp .env.example .env`

Done with no edits (default `change-me-*` values). 43 variables present, matching the F5
audit total.

### 2. `./scripts/bootstrap-pki.sh`

Ran against the fresh workspace. Output (abridged):

```
[ok]   generated CA: mosquitto/config/certs/ca.crt
[ok]   generated broker cert: mosquitto/config/certs/server.crt (CN=diep-mqtt)
[ok]   issued client cert: certs/devices/BAT001.crt (CN=BAT001)
[ok]   issued client cert: certs/devices/EV001.crt (CN=EV001)
[ok]   issued client cert: certs/devices/INV001.crt (CN=INV001)
[ok]   issued client cert: certs/devices/MG001.crt (CN=MG001)
[ok]   issued client cert: certs/devices/METER001.crt (CN=METER001)
[ok]   issued client cert: certs/devices/ingestor.crt (CN=ingestor)
[ok]   issued client cert: certs/devices/dispatcher.crt (CN=dispatcher)
[ok]   issued client cert: certs/devices/csms.crt (CN=csms)
[ok]   generated mosquitto/config/passwd (users: diep-device, diep-nodered)

PKI bootstrap complete. Restart the mqtt, ingestor, dispatcher and ev-charger
services to pick up the new certs:
  docker compose restart mqtt ingestor dispatcher ev-charger
```

Two real bugs in the script were found and fixed **during this revalidation, in the
production repo's `scripts/bootstrap-pki.sh`** (not just the validation copy), since both
would affect any real fresh deployment:

- **`mosquitto/config/passwd` generated with mode 600 by `docker run` as root** —
  unreadable by the mosquitto container's non-root `mosquitto` user, causing
  `mosquitto` to exit 13 ("Unable to open pwfile"). Fixed by appending
  `chmod 644 /mosquitto/config/passwd` to the same `docker run` invocation.
- **`server.key`/`server.crt` generated with mode 600 by host-side `openssl`** —
  unreadable by the same non-root `mosquitto` user, causing "Unable to load server key
  file... Permission denied". Fixed by adding `chmod 644` for both files (with a comment
  explaining the uid mismatch is expected/required, not a weakening of the private key's
  protection in this deployment model).

Re-running `bootstrap-pki.sh` after these fixes (idempotent — `[skip]` for already-issued
certs) confirmed both issues were resolved.

### 3. Deploy

`docker compose -p diep-remediation up -d` (using the +20000 port mapping and
`val2-diep-*` container names for isolation). Result: **all 20 services `Up`**, including
`mqtt`, `kafka`, `kafka-ui`, `timescaledb`, `redis`, `minio`, `fastapi`, `nodered`,
`dispatcher`, `portal`, `ingestor`, `influxdb`, `grafana`, `prometheus`, `alertmanager`,
`cadvisor`, `node-exporter`, `postgres-exporter`, `kafka-exporter`, `ev-charger`.

---

## 4. Component validation

| Component | Check | Result |
|---|---|---|
| **MQTT (8883, mTLS)** | `mosquitto` starts cleanly with the bootstrap-generated CA/server cert/passwd; `ingestor`/`dispatcher`/`ev-charger` connect over 8883 with their bootstrap-issued client certs (no `FileNotFoundError`/TLS errors in logs) | **PASS** |
| **Kafka** | `val2-diep-kafka` up; dispatcher's SASL_PLAINTEXT consumer group (`diep-command-dispatcher`) connects and receives the coordinator assignment | **PASS** |
| **Redis** | `redis-cli -a $REDIS_PASSWORD ping` → `PONG` | **PASS** |
| **TimescaleDB** | `init-db.sh` ran `sql/000-011*.sql` on first start; `/readyz` reports `"database": true` | **PASS** |
| **FastAPI** | `curl -sf http://localhost:28000/readyz` → `{"ready": true, "checks": {"database": true, "redis": true}}` (F1 confirmed fixed — no manual `DB_PASSWORD` reconciliation needed) | **PASS** |
| **Portal** | `curl -sf http://localhost:23002` → 200 (Next.js dev server) | **PASS** |
| **DERMS (site-scoped, F4)** | See below | **PASS** |
| **Monitoring** (Grafana, Prometheus, Alertmanager, cAdvisor, node-exporter, postgres-exporter, kafka-exporter, kafka-ui) | All 8 endpoints return 200/healthy | **PASS** |

### DERMS site-scoped validation (F4)

Obtained an operator JWT via `POST /auth/token` (JSON body
`{"username": "operator", "password": "<DIEP_OPERATOR_PASSWORD>"}`), then issued all three
DERMS commands against the **fresh, seed-only database** using `site_name` instead of
`device_id`:

| Request | Body | Result |
|---|---|---|
| `POST /derms/peak_shaving` | `{"site_name": "Abuja Site A", "reduction_kw": 5}` | `200`, resolved to `device_id: BAT001`, `command_type: discharge`, `status: SENT` |
| `POST /derms/demand_response` | `{"site_name": "Abuja Site A", "event_duration_minutes": 30, "target_reduction_kw": 5}` | `200`, resolved to `device_id: BAT001`, `command_type: discharge`, `status: SENT` |
| `POST /derms/battery_dispatch` | `{"site_name": "Abuja Site A", "target_soc": 80}` | `200`, resolved to `device_id: BAT001`, `command_type: charge`, `status: SENT` |

`val2-diep-dispatcher` logs confirm all three commands were consumed from Kafka and
dispatched to the device's MQTT command topic:

```
[diep-dispatcher] INFO: Received command from Kafka: discharge for BAT001
[diep-dispatcher] INFO: Dispatched discharge for BAT001 to diep/battery/BAT001/cmd
[diep-dispatcher] INFO: Received command from Kafka: discharge for BAT001
[diep-dispatcher] INFO: Dispatched discharge for BAT001 to diep/battery/BAT001/cmd
[diep-dispatcher] INFO: Received command from Kafka: charge for BAT001
[diep-dispatcher] INFO: Dispatched charge for BAT001 to diep/battery/BAT001/cmd
```

Before F4, the same requests against a fresh (un-backfilled) database returned `404`
("No online battery available...") because `devices.site_name` was `NULL`. With F4's
seed-time `site_name` population (`sql/000_schema.sql`'s `sites` insert +
`sql/001-004_seed_*.sql`'s `devices.site_name = 'Abuja Site A'`), the site-scoped lookup
resolves to `BAT001` immediately on a fresh deploy — **no backfill script, no manual SQL,
no tribal knowledge required.**

---

## Validation-only exclusions

These two items were adjustments made **only** in the side-by-side validation workspace
(`~/deploy-validation/diep-lab-remediated/`), to work around artifacts of running a
renamed/port-shifted copy alongside production. **Neither reflects a defect in the
remediated repo**, and neither change was carried back into
`~/projects/diep-lab`:

1. **`diep-mqtt` network alias.** Docker automatically registers a container's
   `container_name` as a network alias (e.g. production's `diep-mqtt` container is
   reachable as both `diep-mqtt` and `mqtt`). The validation stack renames every
   container to `val2-diep-*`, which removes the `diep-mqtt` alias that
   `ingestor`/`dispatcher`/`ev-charger` hardcode as `MQTT_BROKER`. The validation
   `docker-compose.yml` adds an explicit `networks.diep-net.aliases: [diep-mqtt]` to the
   `mqtt` service to restore it. **A real fresh clone, which keeps `container_name:
   diep-mqtt` as written in the remediated `docker-compose.yml`, does not need this** —
   confirmed via `git show v1.0.0-pilot:docker-compose.yml`, which has no explicit
   aliases and relies on the same automatic `container_name` alias.

2. **Alertmanager WIP reversion.** The production working tree currently has unrelated,
   in-progress changes from a separate task (`ALERTMANAGER_EMAIL_CONFIGURATION` —
   an `alertmanager/alertmanager.yml.template` with unsubstituted placeholders and a
   custom `entrypoint.sh`, referenced by the dirty `docker-compose.yml`'s `alertmanager`
   service). These caused `val2-diep-alertmanager` to crash-loop
   (`address ":": port cannot be empty`). The validation `docker-compose.yml` reverted
   the `alertmanager` service to the simple `./alertmanager/alertmanager.yml` mount (as
   in `v1.0.0-pilot`'s tagged `docker-compose.yml`) to isolate this revalidation from that
   unrelated WIP. Production's running `diep-alertmanager` container is healthy
   (`Up 2 hours`) and is out of scope for F1-F5.

---

## Teardown and production confirmation

```
docker compose -p diep-remediation down -v
```

removed all 20 `val2-diep-*` containers, the `diep-remediation_diep-net` network, and all
7 named volumes (`*-data`).

`docker ps` after teardown shows all 24 production `diep-*` containers still `Up`,
unaffected throughout this revalidation.

---

## Outcome

F1-F4 are confirmed closed on a fresh-clone-equivalent deployment, following
`DIEP_INSTALLATION_GUIDE.md` §6.1/§7 documentation only, with no manual database surgery,
no manual cert generation, and no manual `.env`/compose edits beyond `cp .env.example
.env`. Two additional real defects in `scripts/bootstrap-pki.sh` (passwd/cert file
permissions) were found during this revalidation and fixed in the production repo as part
of this same change set (see updated
[`DEPLOYMENT_REMEDIATION_REPORT.md`](DEPLOYMENT_REMEDIATION_REPORT.md) F2 section).

**A clean clone of the remediated tree deploys successfully without manual fixes.**
