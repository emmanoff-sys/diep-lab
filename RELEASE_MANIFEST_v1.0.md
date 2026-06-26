# DIEP — Release Manifest v1.0

**Verification date:** 2026-06-26, last updated post-Production-Cutover
(Phase 6 of the Production Cutover sprint).
**Method:** live `docker inspect` + host-side file checksums, captured
after each set of container recreations and verified.

Configuration checksums are `sha256(sort(sha256sum of every file under the
mounted path)) `, truncated to 16 hex chars — a single fingerprint per
mounted directory/file, suitable for detecting any future drift at a
glance. Secrets appearing in startup commands (`--requirepass`,
`--masterauth`) are redacted in this document.

**Release branch (10 of 31 services):** mixed — see the per-row commit SHA;
`fastapi` is now `release/v1.0-rc2` @ `595829e75b6d82b7c10b1fbedc189f528bc3e1a4`
(worktree `.claude/worktrees/rc2-reconciliation`); the other 9 remain on
`release/v1.0-rc-qualification` @ `8180a200b409f8dec991cfef010fa0a64ad3b696`
(worktree `.claude/worktrees/dlms-driver-validation`) — content-identical to
`release/v1.0-rc2` for these 9 services (the rc2 merge touched only
`fastapi/`-area files), so this is a bookkeeping note, not a functional gap.

---

## Group 1 — Correctly sourced from a Release 1.0 worktree (10 services)

| Service | Image | Commit SHA | Worktree path | Config checksum | Startup command | Mounted files |
|---|---|---|---|---|---|---|
| **fastapi** *(cut over to rc2 — Production Cutover, 2026-06-26T14:37Z)* | python:3.12 | `595829e7` (`release/v1.0-rc2`) | `fastapi/` (worktree: `.claude/worktrees/rc2-reconciliation`) | `f521bb9a08bcefc4` | `sh -c "pip install fastapi uvicorn psycopg2-binary influxdb kafka-python redis prometheus-client && uvicorn app:app --host 0.0.0.0 --port 8000"` | `fastapi/` |
| cim | python:3.12 | 8180a200 | `services/cim` | `f75fc08de7dec9f7` | `sh -c "pip install ... && python -m services.cim.service"` | `services/cim` |
| mdm | python:3.12 | 8180a200 | `services/mdm`, `contracts/` | `71e3a81a9efaaf93` | `sh -c "pip install ... && python -m services.mdm.service"` | `services/mdm`, `contracts/`, `certs/devices` |
| ingestor | python:3.12 | 8180a200 | `ingestor/`, `contracts/` | `df9af4f029a91aed` | `sh -c "pip install paho-mqtt requests prometheus-client && python telemetry_ingestor.py"` | `ingestor/`, `contracts/`, `certs/devices` |
| opcua-connector | python:3.12 | 8180a200 | `services/opcua` | `8212d2004359d543` | `sh -c "pip install asyncua pyyaml cryptography prometheus-client paho-mqtt && python -m services.opcua.service"` | `services/opcua`, `certs/devices` |
| node-exporter | prom/node-exporter | 8180a200 | `prometheus/textfile_collector/` | `941af969b4323ca7` | `/bin/node_exporter --collector.textfile.directory=/textfile_collector` | `prometheus/textfile_collector/` |
| **prometheus** *(reconciled this audit)* | prom/prometheus | 8180a200 | `prometheus/alerts.yml`, `prometheus/prometheus.yml`, `prometheus/secrets/` | alerts: `b8867d4a2f91c5f3`, main: `4eec18e902c9bd65` | `/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus` | `prometheus/alerts.yml`, `prometheus/prometheus.yml`, `prometheus/secrets/minio_token` (regenerated this audit, see below) |
| **wal-shipper** *(reconciled this audit)* | minio/mc | 8180a200 | `wal-shipper/`, `prometheus/textfile_collector/` | `4907ed24cd2dc428` | `/bin/sh /scripts/ship-wal.sh` | `wal-shipper/ship-wal.sh`, `prometheus/textfile_collector/` |
| **grafana** *(reconciled this audit)* | grafana/grafana | 8180a200 | `grafana/provisioning/` | `2e5fdf381cc7bd8c` | `/run.sh` | `grafana/provisioning/` |
| **redis-exporter** *(reconciled this audit)* | oliver006/redis_exporter | 8180a200 | n/a — no bind mount; config from worktree's `docker-compose.yml` | n/a | `/redis_exporter` (env: `REDIS_ADDR=redis://diep-redis:6379`, `REDIS_PASSWORD=<redacted>`) | none |

`docker-compose.yml` (worktree, governs fastapi/node-exporter/prometheus/
wal-shipper/grafana/redis-exporter): `f46279c455b3c031`.
`docker-compose-cim.yml`: `523753f5482c0833`.
`docker-compose-ingestor.yml`: `f2de791c0fb6c371`.
`docker-compose-mdm.yml`: `9c01b29fee596a55`.
`docker-compose-opcua.yml`: `3cf890d9ff18203e`.

---

## Group 2 — Running from the main checkout, content verified identical or
functionally inert (19 distinct compose services, 21 containers)

Commit SHA for all of these: main checkout @ `d411dcc16c3dbea450341191fdc301d3fd3ccffa`
(`feature/adms-topology-import`), via `docker-compose.yml` checksum
`6888672e99f143db`.

| Service | Image | Worktree path equivalent | Config checksum (main checkout) | Startup command | Mounted files |
|---|---|---|---|---|---|
| alertmanager | prom/alertmanager | `alertmanager/` | `961c439388a7a77d` | `/bin/sh /etc/alertmanager-template/entrypoint.sh` | `alertmanager.yml.template`, `entrypoint.sh` |
| caddy | caddy:2-alpine | `caddy/Caddyfile` | `ca5959f1e908a4fe` | `caddy run --config /etc/caddy/Caddyfile --adapter caddyfile` | `Caddyfile`, `certs/` (gitignored) |
| cadvisor | gcr.io/cadvisor/cadvisor | n/a (no app code) | n/a | `/usr/bin/cadvisor -logtostderr` | host paths only |
| dispatcher | python:3.12 | `dispatcher/` | `475612cd24a8f654` | `sh -c "pip install kafka-python paho-mqtt requests && python command_dispatcher.py"` | `dispatcher/`, `certs/devices` |
| ev-charger | python:3.12 | `simulator/` | `eec5613ed6f2e241` | `sh -c "pip install paho-mqtt && python ev_charger.py"` | `simulator/`, `certs/devices` |
| influxdb | influxdb:1.8 | n/a (no app code) | n/a | `influxd` | none (decommissioned data path) |
| kafka | apache/kafka:latest | n/a (no app code) | n/a | `/etc/kafka/docker/run` | none |
| kafka-exporter | danielqsj/kafka-exporter | n/a | n/a | `--kafka.server=diep-kafka:9092` | none |
| kafka-ui | provectuslabs/kafka-ui | n/a | n/a | `java ... -jar kafka-ui-api.jar` | none |
| minio | minio/minio | n/a | n/a | `server /data --console-address :9001` | none |
| mqtt | eclipse-mosquitto | `mosquitto/config/` | `9c08dd313a896195` (excl. gitignored `certs`/`passwd`) | `/usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf` | `mosquitto/config/` — **see note**: `acl` is correct only via an uncommitted main-checkout edit |
| nodered | nodered/node-red | `nodered/` | `c8f8e9f576f77389` | `bash -lc "cd /data && npm install && node-red"` | `nodered/` (whole dir) |
| oms-detector | python:3.12 | `oms/` | `0b8ab3621f8de0dd` | `sh -c "pip install -q requests && exec python outage_detector.py"` | `oms/` |
| portal | node:20 | `portal/` | `f6184abd8746aa06` (excl. `node_modules`/`.next`) | `sh -c "npm install && npm run dev -- -p 3000 -H 0.0.0.0"` | `portal/` |
| postgres-exporter | quay.io postgres-exporter | `prometheus/postgres_exporter_queries.yaml` | `a39f2fd9fa90070a` | `--extend.query-path=/etc/postgres_exporter/queries.yaml` | `postgres_exporter_queries.yaml` |
| redis | redis:7-alpine | n/a | n/a | `redis-server --appendonly yes --requirepass <redacted> --masterauth <redacted>` | none |
| redis-replica | redis:7-alpine | n/a | n/a | `redis-server --replicaof 172.18.0.240 6379 --requirepass <redacted> --masterauth <redacted> --replica-read-only yes --appendonly yes` | none |
| redis-sentinel-1/2/3 | redis:7-alpine | `redis-sentinel/` | `de9095d19329413a` | `/bin/sh /etc/redis-sentinel/sentinel-entrypoint.sh` | `sentinel.conf.template`, `sentinel-entrypoint.sh` |
| timescaledb | timescale/timescaledb:latest-pg16 | n/a | n/a | `postgres -c archive_mode=on -c archive_command=... -c archive_timeout=60` | none |

**Note on `prometheus.yml` for this group's reporting purposes**: the
container actually serving Prometheus is now Group 1 (reconciled). Main
checkout's own copy (`44405079da883622`) is retained here only as a record
of what main checkout independently contains, since it's still the file the
host crontab and any future `docker compose up` from the main checkout
would use.

---

## What changed during this audit (configuration checksum deltas)

| Path | Before (main checkout, as previously live) | After (worktree, now live) |
|---|---|---|
| `prometheus/alerts.yml` | `c894e6c9a889c51b` | `b8867d4a2f91c5f3` |
| `prometheus/prometheus.yml` | `44405079da883622` | `4eec18e902c9bd65` (functionally equivalent — comment-only diff) |
| `wal-shipper/` | `48984ffc7c56f3a8` | `4907ed24cd2dc428` |
| `grafana/provisioning/` | `ca6a40c2e5230cb4` | `2e5fdf381cc7bd8c` |
| `prometheus/secrets/minio_token` | regular file (main checkout) | was an empty directory (Docker auto-create artifact) immediately after the first recreation; **regenerated as a regular file copied from the main checkout** before the second recreation — see `SERVICE_RECONCILIATION_REPORT.md` §4.4 |

---

## Production Cutover deployment record (Phase 6, this sprint)

| Field | Value |
|---|---|
| Service | `diep-fastapi` |
| Git commit | `595829e75b6d82b7c10b1fbedc189f528bc3e1a4` |
| Branch | `release/v1.0-rc2` |
| Container ID | `4cedc6e9f36070b48e3375bd6de160915c74a42f05cfed45eaef13eacc663d9d` |
| Image | `python:3.12` |
| Image digest | `sha256:ea7b35cdb10b8a1381848aeb90a434997da25649c86d842d19fe6154c535cd11` (unchanged — same base image as before the cutover; the application code, not the image, changed) |
| Bind mount source | `/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/rc2-reconciliation/fastapi` |
| Configuration checksum | `f521bb9a08bcefc4` |
| Container created | `2026-06-26T14:37:37.893941886Z` |
| Deployment timestamp (this record) | `2026-06-26T14:44:10Z` |
| Operator | emmanoff_lab (via this session) |
| Previous state | `release/v1.0-rc-qualification` @ `2dd9763`, worktree `.claude/worktrees/dlms-driver-validation`, config checksum `26603ac7ec80f448` |
| Cutover duration | ~14.5s (`docker compose up --force-recreate`) + ~12s to pass `/readyz` (pip install + uvicorn boot) = ~26s total to fully ready |

## Reproducibility statement

As of this manifest's verification date, **10 of 31 running containers**
(Group 1) can be exactly reproduced by running `docker compose -p diep-lab
--project-directory <worktree> -f <compose-file> up -d` against the
Release 1.0 worktree. The remaining **21** (Group 2) can be reproduced from
the main checkout's current `docker-compose.yml` and tracked files, **except**:

- `diep-redis-exporter`'s pre-reconciliation configuration could not have
  been reproduced from any file in either checkout (now resolved — it is
  Group 1).
- `diep-wal-shipper`'s pre-reconciliation configuration could not have been
  reproduced either (now resolved — it is Group 1).
- `mosquitto/config/acl`'s currently-correct content has no committed home
  on the main checkout's branch (still open — see
  `CONFIGURATION_DRIFT_REPORT.md` Part 3).
- The host cron jobs for `backup-db.sh`/`backup-pg-basebackup.sh` run
  scripts that, as committed on the main checkout's branch, lack the
  freshness-metric code present in the Release 1.0 worktree's versions
  (still open — see `FINAL_RELEASE_RECOMMENDATION.md`).
