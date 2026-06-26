# DIEP v1.0 — Deployment Inventory

**Date:** 2026-06-26
**Method:** `docker inspect` against every running container on the live host
(no assumptions from compose files or prior reports). 31 containers running
at inventory time.

**Reference commits at inventory time:**
- RC worktree (`Release 1.0` source tree): `.claude/worktrees/dlms-driver-validation`,
  branch `release/v1.0-rc-qualification`, commit `8180a200b409f8dec991cfef010fa0a64ad3b696`.
- Main checkout: `/home/emmanoff_lab/projects/diep-lab`, branch
  `feature/adms-topology-import`, commit `d411dcc16c3dbea450341191fdc301d3fd3ccffa`,
  **with 3 uncommitted working-tree edits** (see note after the table —
  `mosquitto/config/acl`, `nodered/.config.users.json`, `prometheus/prometheus.yml`).

---

## Full inventory

| Container | Image | Image digest (short) | Container ID | Restarts | Compose project | Compose file used at creation | Bind-mounted source (host path) | Named volumes | Source tree / branch / commit |
|---|---|---|---|---|---|---|---|---|---|
| diep-alertmanager | prom/alertmanager | af26fbe4dd18 | b4baa3a8ac6f | 0 | diep-lab | main checkout `docker-compose.yml` | `alertmanager/alertmanager.yml.template`, `alertmanager/entrypoint.sh` | anon volume `/alertmanager` | main checkout @ d411dcc1 — **content identical** to worktree's copy |
| diep-caddy | caddy:2-alpine | c2af7d900485 | d068bcc27b7f | 0 | diep-lab | main checkout `docker-compose.yml` | `caddy/Caddyfile`, `caddy/certs` (gitignored, generated) | — | main checkout @ d411dcc1 — Caddyfile **identical** to worktree's |
| diep-cadvisor | gcr.io/cadvisor/cadvisor | 3de2bd520312 | dbfc8850b387 | 0 | diep-lab | main checkout `docker-compose.yml` | host paths only (`/`, `/sys`, `/var/lib/docker`, `/var/run`) — no app code | — | N/A — no app-code bind mount; config is compose env/flags only |
| diep-cim | python:3.12 | ea7b35cdb10b | 46d89935256a | 0 | dlms-driver-validation | worktree `docker-compose-cim.yml` | `services/cim` | — | **worktree @ 8180a200 — correct** |
| diep-dispatcher | python:3.12 | ea7b35cdb10b | 560f64907bb3 | 15 | diep-lab | main checkout `docker-compose.yml` | `dispatcher/`, `certs/devices` (gitignored) | — | main checkout @ d411dcc1 — **content identical** to worktree's `dispatcher/`. Restart count of 15 is a pre-existing operational signal, not a deployment-source issue (last restart exit code 0) — out of this sprint's scope, noted for awareness. |
| diep-ev-charger | python:3.12 | ea7b35cdb10b | 1e149d6f5799 | 0 | diep-lab | main checkout `docker-compose.yml` | `simulator/`, `certs/devices` | — | main checkout @ d411dcc1 — **content identical** to worktree's `simulator/` |
| diep-fastapi | python:3.12 | ea7b35cdb10b | 30e510cfd86e | 0 | diep-lab | worktree `docker-compose.yml` | `fastapi/` | — | **worktree @ 8180a200 — correct** (corrected this engagement, prior task) |
| diep-grafana | grafana/grafana | 121a7a9ece6d | dba381e83e26 | 0 | diep-lab | main checkout `docker-compose.yml` | `grafana/provisioning/` | volume `grafana-data` | main checkout @ d411dcc1 — provisioning identical **except missing** `dashboards/ami-mdm-pipeline.json` (present only in worktree) |
| diep-influxdb | influxdb:1.8 | 299ebda2c7e3 | 249336d4dbe3 | 0 | diep-lab | main checkout `docker-compose.yml` | none (decommissioned data path; no app code mount) | volume `influxdb-data` | N/A — no app-code bind mount |
| diep-ingestor | python:3.12 | ea7b35cdb10b | d0be0f760abb | 0 | dlms-driver-validation | worktree `docker-compose-ingestor.yml` | `ingestor/`, `contracts/`, `certs/devices` | — | **worktree @ 8180a200 — correct** |
| diep-kafka | apache/kafka:latest | 9516fb7634ba | 4bd85c72539c | 0 | diep-lab | main checkout `docker-compose.yml` | none | volume `kafka-data` + 2 anon (secrets, shared config) | N/A — no app-code bind mount; compose service block confirmed byte-identical between checkouts |
| diep-kafka-exporter | danielqsj/kafka-exporter | a51b280b55a7 | 5d827b3138a4 | 0 | diep-lab | main checkout `docker-compose.yml` | none | — | N/A — no app-code bind mount |
| diep-kafka-ui | provectuslabs/kafka-ui | 8f2ff02d64b0 | 9043398fb300 | 0 | diep-lab | main checkout `docker-compose.yml` | none | — | N/A — no app-code bind mount |
| diep-mdm | python:3.12 | ea7b35cdb10b | 4f2fec740c35 | 0 | dlms-driver-validation | worktree `docker-compose-mdm.yml` | `services/mdm`, `contracts/`, `certs/devices` | — | **worktree @ 8180a200 — correct** |
| diep-minio | minio/minio | 14cea493d9a3 | 78f0878a3d80 | 0 | diep-lab | main checkout `docker-compose.yml` | none | volume `minio-data` | N/A — no app-code bind mount |
| diep-mqtt | eclipse-mosquitto | 6f8d8a947c50 | 70cda2526177 | 0 | diep-lab | main checkout `docker-compose.yml` | `mosquitto/config/` (+ gitignored `certs`, `passwd`) | volumes `data`, `log` | main checkout @ d411dcc1 **plus an uncommitted working-tree edit to `acl`** — see note below. Live content is currently correct (matches worktree) but is not committed on this checkout's branch. |
| diep-node-exporter | prom/node-exporter | e9cff4fc67b1 | e360da51d6dc | 0 | diep-lab | worktree `docker-compose.yml` | `prometheus/textfile_collector/` | — | **worktree @ 8180a200 — correct** (corrected this engagement, prior task) |
| diep-nodered | nodered/node-red | 153f411d2993 | 9fc303f1ae66 | 0 | diep-lab | main checkout `docker-compose.yml` | `nodered/` (whole dir) | — | main checkout @ d411dcc1 — all tracked files **identical** except `.config.users.json` (editor UI tour-state only, not functional) |
| diep-oms-detector | python:3.12 | ea7b35cdb10b | 37c6c2a768c2 | 0 | diep-lab | main checkout `docker-compose.yml` | `oms/` | — | main checkout @ d411dcc1 — **content identical** to worktree's `oms/` |
| diep-opcua-connector | python:3.12 | ea7b35cdb10b | 05c1564b3d7d | 0 | dlms-driver-validation | worktree `docker-compose-opcua.yml` | `services/opcua`, `certs/devices` | — | **worktree @ 8180a200 — correct** |
| diep-portal | node:20 | 8f693eaa7e0a | 9dd9153d0b07 | 0 | diep-lab | main checkout `docker-compose.yml` | `portal/` | — | main checkout @ d411dcc1 — identical except `next-env.d.ts` (gitignored, auto-generated Next.js boilerplate, "should not be edited") and `node_modules` (build artifact) |
| diep-postgres-exporter | quay.io postgres-exporter | e96064f87622 | 9dc9bba261fb | 0 | diep-lab | main checkout `docker-compose.yml` | `prometheus/postgres_exporter_queries.yaml` | — | main checkout @ d411dcc1 — **content identical** |
| diep-prometheus | prom/prometheus | a75c5a35bc21 | b6fc1efdb6e0 | 0 | diep-lab | main checkout `docker-compose.yml` | `prometheus/alerts.yml`, `prometheus/prometheus.yml`, `prometheus/secrets/` | volume `prometheus-data` | main checkout @ d411dcc1 (`prometheus.yml` has an uncommitted edit, see note — functionally a no-op vs. worktree). **`alerts.yml` is genuinely missing 6 rules present in the worktree's committed version — confirmed not loaded via live `/api/v1/rules`.** See `CONFIGURATION_DRIFT_REPORT.md`. |
| diep-redis | redis:7-alpine | 6ab0b6e73817 | f72f356b778c | 0 | diep-lab | main checkout `docker-compose.yml` | none | volume `redis-data` | N/A — compose service block confirmed identical between checkouts |
| diep-redis-exporter | oliver006/redis_exporter | 2e9795be900d | a6a503d8448b | 0 | diep-lab | main checkout `docker-compose.yml` (**label only — see note**) | none | — | **Anomaly**: created 2026-06-25T11:48:03Z with env vars matching the worktree's `docker-compose.yml` `redis-exporter` service definition exactly, but main checkout's *current, committed* `docker-compose.yml` does not define a `redis-exporter` service at all (confirmed: `grep` finds nothing). The container's actual running configuration cannot be reproduced by re-running `docker compose up` against any file currently on disk in main checkout. See drift report. |
| diep-redis-replica | redis:7-alpine | 6ab0b6e73817 | 24529db5c094 | 0 | diep-lab | main checkout `docker-compose.yml` | none | volume `redis-replica-data` | N/A — compose service block identical between checkouts |
| diep-redis-sentinel-1/2/3 | redis:7-alpine | 6ab0b6e73817 | 86f0bf6823c4 / 421d80e2df0b / f5c9204b6cbb | 0 | diep-lab | main checkout `docker-compose.yml` | `redis-sentinel/sentinel.conf.template`, `sentinel-entrypoint.sh` | volumes `redis-sentinel-{1,2,3}-data` | main checkout @ d411dcc1 — **content identical** to worktree's |
| diep-timescaledb | timescale/timescaledb:latest-pg16 | fdce0a44280d | 99773216ba39 | 0 | diep-lab | main checkout `docker-compose.yml` | none | volumes `timescale-data`, `wal-archive` | N/A — compose service block identical between checkouts |
| diep-wal-shipper | minio/mc | a7fe349ef4bd | 5cb820557963 | 0 | diep-lab | main checkout `docker-compose.yml` (**label only — see note**) | `wal-shipper/ship-wal.sh`, `prometheus/textfile_collector/` (this 2nd mount **does not exist** in main checkout's current `docker-compose.yml`) | volume `wal-archive` | **Anomaly, same class as redis-exporter**: created 2026-06-25T11:46:06Z with a bind mount (`textfile_collector`) that main checkout's current, committed `docker-compose.yml` does not define for this service. The mounted *script* (`ship-wal.sh`) is also main checkout's, which never (in its committed git history on this branch) contained the freshness-metric write — yet a fresh metric file is observed in that same mounted directory. Not explainable from host-level evidence alone (live container internals were not inspected — see Known Limitations of this audit). See drift report. |

---

## Note: uncommitted live edits in the main checkout

The main checkout (`/home/emmanoff_lab/projects/diep-lab`, branch
`feature/adms-topology-import`) has 3 files modified in its working tree,
**none committed to any branch from this checkout**, all 3 of which are
live bind-mount sources for running containers:

| File | Live container(s) | Nature of the edit | Risk |
|---|---|---|---|
| `mosquitto/config/acl` | diep-mqtt | Adds `topic readwrite diep/+/+/trusted` for the `ingestor` user | **Currently byte-identical to the worktree's committed version** — safe today only because the same content happens to be committed on a different branch. A `git checkout --` or reset of this working tree would silently remove a grant the MDM→ingestor trusted-topic path depends on. |
| `prometheus/prometheus.yml` | diep-prometheus | Adds `redis-exporter`, `diep-mdm`, `diep-opcua-connector` scrape jobs (comments differ from the worktree's version, but the jobs themselves are identical) | Same risk as above — functionally fine today, safe net only because of an unrelated branch's commit. |
| `nodered/.config.users.json` | diep-nodered | Editor UI tour/sidebar state only | None — not functional configuration. |

This is documented in full in `CONFIGURATION_DRIFT_REPORT.md`.

## Known limitation of this inventory

Container-internal state (the actual bytes a long-running process has in
memory, as opposed to what's currently on disk at its bind-mount source)
was **not** inspected via `docker exec` for any container beyond what
host-side file comparison and live HTTP APIs (Prometheus's own
`/api/v1/rules`) could confirm. This is a deliberate boundary for this
audit, not an oversight — shell access into live, unscoped production
containers was correctly treated as requiring its own explicit
authorization, which was not sought for this pass. Where this matters
(`diep-wal-shipper`), it is called out explicitly above rather than
glossed over.
