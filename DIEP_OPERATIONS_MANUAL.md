# DIEP Operations Manual (Phase 16, Task 3)

**Date:** 2026-06-13
**Scope:** Day-2 operations procedures for the DIEP pilot platform — startup, shutdown,
backup, restore, disaster recovery, and monitoring. This manual consolidates and
cross-references the scripts and runbooks produced in Phases 10 and 15C; it adds no new
scripts or configuration.

---

## 1. Startup procedures

### 1.1 Full stack startup

```bash
cd ~/projects/diep-lab
./start-all-diep.sh
```

This script:
1. `docker compose up -d` — starts all 25 services defined in `docker-compose.yml`
   (plus any active profile overlays).
2. Runs `./init-db.sh` — applies the TimescaleDB schema and seed data (idempotent;
   safe on an already-initialized database).
3. Waits for Node-RED (`http://localhost:1880`) to come up, then deploys flows via
   `nodered/rebuild_flows.py`.
4. Prints `docker compose ps` and a summary of service URLs.

### 1.2 Partial / overlay startup

Additional device or HA overlays are started by `-f`-chaining the relevant
`docker-compose-*.yml` file, e.g.:

```bash
docker compose -f docker-compose.yml -f docker-compose-ha.yml up -d
```

### 1.3 Post-startup verification

```bash
curl -sf http://localhost:8000/healthz   # liveness
curl -sf http://localhost:8000/readyz    # readiness (DB + Redis)
docker compose ps                        # all services "Up" / "Up (healthy)"
```

Expect `/readyz` → `{"ready": true, "checks": {"database": true, "redis": true}}`.

---

## 2. Shutdown procedures

### 2.1 Graceful full-stack shutdown

```bash
cd ~/projects/diep-lab
docker compose down
```

This stops and removes all containers but **preserves** the seven named volumes
(`timescale-data`, `kafka-data`, `redis-data`, `minio-data`, `grafana-data`,
`prometheus-data`, `influxdb-data`) — data is retained across a down/up cycle.

> Do **not** add `-v`/`--volumes` to `docker compose down` unless a full data wipe is
> intended — this would destroy TimescaleDB, Kafka, Redis, MinIO, Grafana, and
> Prometheus data.

### 2.2 Single-service restart (preferred for transient issues)

```bash
docker restart <container-name>     # e.g. diep-fastapi, diep-kafka, diep-timescaledb
```

Per the Phase 15C DR drill (§3 of `PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`), restarting
TimescaleDB, MQTT, Grafana, and FastAPI recovers in under 20 seconds; Kafka recovers in
~20 seconds **provided its checkpoint files are healthy** (see §5 below for the
known historical issue and fix).

### 2.2a OMS detector (`diep-oms-detector`)

The outage-detection runner is a first-class service in the main stack. It polls
`POST /oms/detect` every `OMS_DETECT_INTERVAL` seconds (default 30) and has a
heartbeat **healthcheck** — it writes `OMS_HEARTBEAT_FILE` after every sweep and is
reported unhealthy if that file goes stale for >90s (3 missed sweeps).

```bash
docker inspect -f '{{.State.Health.Status}}' diep-oms-detector   # healthy | unhealthy
docker logs diep-oms-detector | grep detection:                  # case create/restore activity
```

It holds **no local state**: detection is server-side and idempotent (re-derives
from current DB state each sweep), so `docker restart diep-oms-detector` resumes
cleanly with no recovery step. If it shows `unhealthy`, check FastAPI reachability
first (`/oms/detect` returning non-200 is logged as a warning) — the detector keeps
retrying through transient API outages by design and does not need intervention for
those. Health reflects only that the poll loop itself is alive.

### 2.3 Partial subset of `restart-diep.sh`

`restart-diep.sh` exists as a legacy convenience script that starts a subset of
monitoring/legacy containers (`diep-prometheus`, `diep-grafana`, `diep-node-exporter`,
`diep-cadvisor`, `diep-mqtt`, `diep-influxdb`, `diep-nodered`, `diep-smartmeter`). It does
**not** cover the full 25-container stack — prefer `docker compose up -d` /
`./start-all-diep.sh` for full recovery.

---

## 3. Backup procedures

Full detail: [`PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`](PHASE15C_PRODUCTION_OPERATIONS_REPORT.md) §1-2.

### 3.1 Scheduled backups (installed crontab)

```bash
crontab -l | grep diep-backup
```

| Time | Job | Script |
|---|---|---|
| 02:00 daily | Database backup (pg_dump custom format, checksum, MinIO + local archive, retention prune) | `scripts/backup-db.sh` |
| 02:30 daily | Configuration backup (compose files, MQTT certs/config, Alertmanager, Grafana provisioning, Prometheus config — `.env` excluded) | `scripts/backup-config.sh` |
| 03:00 Sunday | Backup verification (checksum + restore-into-scratch-DB drill) | `scripts/verify-backup.sh` |

Logs: `backups/logs/{backup-db,backup-config,verify-backup}.log`.

### 3.2 Manual / on-demand backup

```bash
cd ~/projects/diep-lab
./scripts/backup-db.sh        # database
./scripts/backup-config.sh    # configuration
./scripts/verify-backup.sh    # verify the most recent dump
```

### 3.3 Backup retention

- `BACKUP_RETENTION_DAYS` (default 14) — applies to both local archive (`backups/`,
  `backups/config/`) and the MinIO buckets (`diep-db-backups`, `diep-config-backups`),
  pruned via `mc rm --force --older-than`.

---

## 4. Restore procedures

Full detail with exact commands: [`PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`](PHASE15C_PRODUCTION_OPERATIONS_REPORT.md) §1 ("Restore runbook").

### 4.1 Drill restore (verification only — does not touch production data)

```bash
./scripts/restore-db.sh <dump-file>
```
Restores into a scratch database (`diep_restore_test`), reports row-count comparisons
against the source dump, then drops the scratch database. This is what `verify-backup.sh`
runs weekly.

### 4.2 Disaster restore (into the real `diep` database — DESTRUCTIVE, requires confirmation)

High-level sequence (see Phase 15C report for full commands):
1. Stop application writers (`fastapi`, `ingestor`, `dispatcher`) to prevent writes
   during restore.
2. `SELECT timescaledb_pre_restore();` on the target database.
3. `pg_restore` the chosen dump into `diep`.
4. `SELECT timescaledb_post_restore();` to re-enable background jobs.
5. Restart application services and verify via `/readyz` and a telemetry write.

This path is destructive to current data in `diep` and must only be run as part of an
actual disaster recovery, with the user's explicit go-ahead.

### 4.3 Configuration restore

Extract the relevant subtree from `backups/config/diep-config_<timestamp>.tar.gz`
(or the MinIO copy) over the corresponding path under the project root, then
`docker compose up -d <affected-service>` to pick up the restored config.
`.env` is **not** included in config backups (Phase 15A) — restore secrets from
a secrets vault/manager separately.

---

## 5. Disaster recovery (DR) procedures

Full detail with measured RTOs and a real fixed incident:
[`PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`](PHASE15C_PRODUCTION_OPERATIONS_REPORT.md) §3.

### 5.1 Non-destructive DR drill

```bash
./scripts/dr-test.sh                 # all 5 core services
./scripts/dr-test.sh kafka           # single service
```

Restarts each service's container (data volumes untouched) and measures time-to-healthy
(RTO proxy). Last measured results: TimescaleDB 2.8s, MQTT 2.7s, Kafka 19.6s, Grafana
11.1s, FastAPI 16.0s.

### 5.2 Known Kafka checkpoint-corruption failure mode

If Kafka enters a restart-crash loop (`docker logs diep-kafka` shows
`Error while reading checkpoint file ... Shutdown broker because all log dirs ... have failed`),
the on-disk checkpoint files (`log-start-offset-checkpoint`,
`replication-offset-checkpoint`, `cleaner-offset-checkpoint`) under the `kafka-data`
volume are corrupted. Fix (does not touch topic/message data):

```bash
docker stop diep-kafka
docker run --rm -v diep-lab_kafka-data:/data alpine sh -c \
  "printf '0\n0\n' > /data/log-start-offset-checkpoint && \
   printf '0\n0\n' > /data/replication-offset-checkpoint && \
   printf '0\n0\n' > /data/cleaner-offset-checkpoint && \
   chown 1000:1000 /data/log-start-offset-checkpoint /data/replication-offset-checkpoint /data/cleaner-offset-checkpoint"
docker start diep-kafka
```

Verify with `docker exec diep-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list`.

### 5.3 RTO/RPO targets vs. current

| Metric | Target (Phase 10E) | Current |
|---|---|---|
| RTO | ≤ 30 min | ≤ 20s for all 5 services drilled (process/container restart) |
| RPO | ≤ 5 min | ~24h (nightly `pg_dump` only — no PITR/WAL archiving yet) |

Closing the RPO gap requires Postgres PITR/WAL archiving (K3 in the HA roadmap,
`DIEP_HA_ARCHITECTURE.md` §3, re-prioritized in the Phase 15C report §4).

---

## 6. Monitoring procedures

### 6.1 Dashboards and endpoints

| Tool | URL | Purpose |
|---|---|---|
| Grafana | http://localhost:3001 | Dashboards (provisioned via `grafana/provisioning`) |
| Prometheus | http://localhost:9090 | Metrics, alert rule status (`/alerts`) |
| Alertmanager | http://localhost:9093 | Active alerts, silences |
| cAdvisor | http://localhost:8080 | Per-container resource usage |
| FastAPI `/metrics` | http://localhost:8000/metrics | Application metrics (DERMS requests, commands, etc.) |
| Kafka UI | http://localhost:8081 | Topic/consumer-group inspection |

### 6.2 Key alert rules (Phase 15B, `prometheus/alerts.yml`)

| Alert | Condition | Meaning |
|---|---|---|
| `DiepApiDown` | `up{job="diep-fastapi"} == 0` | FastAPI unreachable by Prometheus |
| `DatabaseOutage` | `up{job="postgres-exporter"} == 0` or `pg_up == 0` | TimescaleDB down/unreachable |
| `KafkaOutage` | `up{job="kafka-exporter"} == 0` or `kafka_brokers == 0` | Kafka broker(s) down |
| `MQTTDown` | `absent(container_memory_usage_bytes{name="diep-mqtt"})` | MQTT container not running |
| `GrafanaDown` | `absent(container_memory_usage_bytes{name="diep-grafana"})` | Grafana container not running |
| `HighCPUUsage` / `HighMemoryUsage` | node CPU/mem > 80%/85% for 2m | Host resource pressure |
| `PrometheusDown` / `NodeExporterDown` / `CadvisorDown` | exporter scrape failures | Monitoring pipeline health |

**Known gap (Task 5 report):** Alertmanager's `default` receiver has no notification
integration configured (no email/Slack/webhook) — alerts fire but produce no external
notification. Configuring a receiver is a pre-go-live action item.

### 6.3 Daily operational checks

```bash
docker compose ps                                  # all containers Up/healthy
curl -sf http://localhost:8000/readyz              # API + DB + Redis
curl -sf http://localhost:9090/-/healthy           # Prometheus
curl -sf http://localhost:3001/api/health           # Grafana
tail -5 backups/logs/backup-db.log                  # last night's backup ran
```

### 6.4 Weekly operational checks

```bash
tail -20 backups/logs/verify-backup.log             # Sunday verify-restore drill PASS
./scripts/dr-test.sh                                # optional: re-run DR drill
```

---

## 7. Escalation / incident response

See [`PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`](PHASE15C_PRODUCTION_OPERATIONS_REPORT.md) §5
for the full 6-step detect → triage → contain → recover → verify → postmortem workflow.
