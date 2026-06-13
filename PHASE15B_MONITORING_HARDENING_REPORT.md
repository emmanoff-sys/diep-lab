# Phase 15B — Monitoring & Observability Hardening Report

**Project:** DIEP Lab (`~/projects/diep-lab`)
**Date:** 2026-06-11
**Starting readiness:** ~80/100 (post Phase 15A security hardening)
**Scope:** Monitoring/observability only — no application logic, business workflow,
or DERMS functionality was modified.

---

## 1. Summary of Changes

### Task 1 — PostgreSQL / TimescaleDB Monitoring

| Change | File(s) |
|---|---|
| Enabled `pg_stat_statements` (added to `shared_preload_libraries`, extension created) | TimescaleDB config (`ALTER SYSTEM`), container restarted |
| Added `postgres-exporter` service (`quay.io/prometheuscommunity/postgres-exporter`), port `9187`, connects to `diep-timescaledb` using `${DB_USER}`/`${DB_PASSWORD}` from `.env` | `docker-compose.yml` |
| Added custom-query file for TimescaleDB hypertable size/chunks, compression stats, and `pg_stat_statements` top-query rollup | `prometheus/postgres_exporter_queries.yaml` (new) |
| Added Prometheus scrape job `postgres-exporter` | `prometheus/prometheus.yml` |
| New Grafana dashboard "DIEP PostgreSQL / TimescaleDB" — connections, DB size, transaction rate, top queries (`pg_stat_statements`), hypertable size/chunks, compression ratio, exporter up/down | `grafana/provisioning/dashboards/postgres-timescaledb.json` (new) |
| New alert: `DatabaseOutage` (`up{job="postgres-exporter"}==0 or pg_up==0`) | `prometheus/alerts.yml` |

### Task 2 — Kafka Monitoring

| Change | File(s) |
|---|---|
| Added `kafka-exporter` service (`danielqsj/kafka-exporter`), port `9308`, points at `diep-kafka:9092` (internal PLAINTEXT listener) | `docker-compose.yml` |
| Added Prometheus scrape job `kafka-exporter` | `prometheus/prometheus.yml` |
| New Grafana dashboard "DIEP Kafka" — broker count, exporter up/down, topic partition counts, per-topic message rate, consumer-group lag, consumer-group offsets/members | `grafana/provisioning/dashboards/kafka.json` (new) |
| New alert: `KafkaOutage` (`up{job="kafka-exporter"}==0 or kafka_brokers==0`) | `prometheus/alerts.yml` |

### Task 3 — Alertmanager

| Change | File(s) |
|---|---|
| Replaced the empty single-receiver config with severity-based routing: `route` groups by `alertname, severity`; `severity: critical` → `critical` receiver (1h repeat); `severity: warning` → `warning` receiver; everything else → `default` | `alertmanager/alertmanager.yml` |
| Added an inhibition rule so `HighCommandFailureRate` (warning) is suppressed while `DiepApiDown` (critical) is active | `alertmanager/alertmanager.yml` |
| Receivers wired as webhook receivers to placeholder URLs (`http://diep-alertmanager-webhook.invalid/...`) — config/routing is fully functional and validated; production must replace these with real Slack/PagerDuty/email endpoints (see §5 Remaining Risks) | `alertmanager/alertmanager.yml` |
| Sample alerts created/confirmed for the four required outage scenarios: `MQTTDown` (pre-existing), `DiepApiDown` (pre-existing, FastAPI), `KafkaOutage` (new), `DatabaseOutage` (new) | `prometheus/alerts.yml` |

### Task 4 — Grafana Cleanup

- Reviewed `grafana/provisioning/datasources/` — only **one** datasource is provisioned (`Prometheus`, uid `prometheus`), and every panel in every dashboard (`command-path.json`, the two new dashboards) references it. **No orphaned datasources found** — no removal needed.
- Confirmed via Grafana API (`/api/datasources`) that exactly one datasource exists post-change.
- Confirmed via Grafana API (`/api/search?type=dash-db`) that all 3 dashboards (Command/Control Plane, Kafka, PostgreSQL/TimescaleDB) auto-provisioned correctly into the "DIEP" folder.

### Files Modified / Added

```
M  docker-compose.yml                              (postgres-exporter, kafka-exporter services)
M  prometheus/prometheus.yml                       (scrape jobs: postgres-exporter, kafka-exporter)
M  prometheus/alerts.yml                           (KafkaOutage, DatabaseOutage alerts)
M  alertmanager/alertmanager.yml                   (severity routing, receivers, inhibition rule)
A  prometheus/postgres_exporter_queries.yaml       (TimescaleDB hypertable/compression/pg_stat_statements queries)
A  grafana/provisioning/dashboards/postgres-timescaledb.json
A  grafana/provisioning/dashboards/kafka.json
```

No backups were required for these files (additive changes / Grafana provisioning is hot-reloaded). The one stateful change — enabling `pg_stat_statements` — is reversible (see §4 Rollback).

---

## 2. Commands Executed

```bash
# Task 1: enable pg_stat_statements (requires shared_preload_libraries + restart)
docker exec diep-timescaledb psql -U diep -d diep -tAc \
  "ALTER SYSTEM SET shared_preload_libraries = 'timescaledb,pg_stat_statements';"
docker compose restart timescaledb
docker exec diep-timescaledb psql -U diep -d diep -tAc \
  "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"

# Bring up new exporters (additive containers — does not touch existing services)
docker compose up -d postgres-exporter kafka-exporter

# Reload Prometheus scrape config + alert rules, and Alertmanager routing
docker compose restart prometheus alertmanager
```

### Operational note (encountered during this phase)

`ALTER SYSTEM SET shared_preload_libraries = 'timescaledb,pg_stat_statements'` wrote a
malformed value to `postgresql.auto.conf` (`'"timescaledb,pg_stat_statements"'` —
double-quoted), which crash-looped `diep-timescaledb` on restart
(`FATAL: could not access file "timescaledb,pg_stat_statements"`). Fixed by mounting
the `timescale-data` volume into a throwaway `alpine` container and correcting the
line with `sed`, then restarting. **No data was lost** — `telemetry` row count and
all hypertable chunks were intact after recovery (verified `select count(*) from
telemetry` → 10234 rows, unchanged). This is now a known gotcha if `shared_preload_libraries`
is ever edited again on this image: verify `postgresql.auto.conf` content before
restarting, or prefer a config-file-based change.

As in Phase 15A: `docker compose restart <svc>` does **not** reload `.env`/compose
changes for already-running containers; new services (`postgres-exporter`,
`kafka-exporter`) were brought up with `docker compose up -d`, while config-file-mount
services (`prometheus`, `alertmanager`) only needed `restart` since their mounted
files changed on the host (bind mounts re-read on restart) — no env/image change involved.

---

## 3. Validation Evidence

### 3a. Prometheus targets — all healthy

```
job              health
cadvisor         up
diep-fastapi     up
kafka-exporter   up
node-exporter    up
postgres-exporter up
prometheus       up
```

### 3b. Postgres exporter — core + custom metrics present

```
pg_up 1
pg_database_size_bytes{datname="diep"} 13179927
pg_stat_database_numbackends{datid="16384",datname="diep"} 3
pg_stat_statements_top_calls{query="SELECT device_type, status, site_name, location FROM devices WHERE device_id = $",...} 182
timescaledb_hypertable_num_chunks{hypertable_name="telemetry",...} 1
timescaledb_hypertable_total_bytes{hypertable_name="telemetry",...} 2113536
timescaledb_compression_total_chunks{hypertable_name="telemetry",...} 1
timescaledb_compression_compressed_chunks{hypertable_name="telemetry",...} 0
```
(Compression stats are 0/0 because no chunks have been compressed yet — this is the
correct, expected value for a low-volume lab dataset and confirms the query executes
without error.)

### 3c. Kafka exporter — broker, topic, consumer-group metrics present

```
kafka_brokers 1
kafka_topic_partitions{topic="diep.commands"} 1
kafka_consumergroup_current_offset{consumergroup="diep-command-dispatcher",partition="0",topic="diep.commands"} 9
kafka_consumergroup_lag_sum{consumergroup="diep-command-dispatcher",topic="diep.commands"} 0
kafka_consumergroup_members{consumergroup="diep-command-dispatcher"} 1
```

### 3d. Prometheus alert rules — all loaded, evaluating `ok`

```
HighCPUUsage ok          NodeExporterDown ok      KafkaOutage ok
HighMemoryUsage ok       CadvisorDown ok          DatabaseOutage ok
PrometheusDown ok        MQTTDown ok              DiepApiDown ok
GrafanaDown ok           HighCommandFailureRate ok / CommandsRejected ok /
                          HighCommandDispatchLatency ok / SlowCommandAck ok
```

### 3e. Alertmanager config — loaded successfully, severity routing active

`GET /api/v2/status` confirms `cluster.status: ready` and the rendered route tree:
- default route → receiver `default`
- `severity: critical` → receiver `critical`, `repeat_interval: 1h`
- `severity: warning` → receiver `warning`
- inhibit rule: `DiepApiDown` (critical) suppresses `HighCommandFailureRate` (same severity label match)

### 3f. End-to-end alert fire/route/resolve test — KafkaOutage

```
docker stop diep-kafka-exporter
# t+~70s: Prometheus alert state -> firing (severity=critical)
# Alertmanager: KafkaOutage critical active, receivers=['critical']
docker start diep-kafka-exporter
# Prometheus target -> up, alert -> resolved (no longer in /api/v1/alerts)
```

### 3g. End-to-end alert fire/route/resolve test — DatabaseOutage

```
docker stop diep-postgres-exporter
# Prometheus alert state: pending -> firing (severity=critical) after the 1m `for`
# Alertmanager: DatabaseOutage critical active, receivers=['critical']
docker start diep-postgres-exporter
# Prometheus target -> up, alert list -> [] (resolved)
```

Both tests demonstrate the full pipeline: exporter down → Prometheus `up==0` →
alert rule fires after `for` duration → routed by `severity: critical` to the
`critical` Alertmanager receiver → resolves automatically when the exporter recovers.

### 3h. Grafana — dashboards provisioned and querying live data

```
GET /api/search?type=dash-db  ->
  DIEP Command/Control Plane  (diep-command-path)
  DIEP Kafka                  (diep-kafka)
  DIEP PostgreSQL / TimescaleDB (diep-postgres-timescaledb)

GET /api/datasources/proxy/uid/prometheus/api/v1/query?query=pg_up
  -> pg_up{job="postgres-exporter"} = 1

GET /api/datasources/proxy/uid/prometheus/api/v1/query?query=kafka_brokers
  -> kafka_brokers{job="kafka-exporter"} = 1

GET /api/datasources/proxy/uid/prometheus/api/v1/query?query=timescaledb_hypertable_total_bytes
  -> timescaledb_hypertable_total_bytes{hypertable_name="telemetry"} = 2334720
```

### 3i. Grafana datasources — no orphans

```
GET /api/datasources -> [ {"name":"Prometheus","uid":"prometheus","url":"http://diep-prometheus:9090", ...} ]
```
Single datasource, referenced by every panel in every provisioned dashboard.

### 3j. Container health — all services up post-change

```
diep-postgres-exporter   Up   (new)
diep-kafka-exporter      Up   (new)
diep-timescaledb         Up   (restarted for pg_stat_statements; data verified intact)
diep-prometheus          Up   (restarted; config reloaded)
diep-alertmanager        Up   (restarted; config reloaded)
... all 22 pre-existing containers remain Up ...
```

---

## 4. Rollback Procedure

All changes are additive/config-only and can be rolled back independently.

1. **Postgres exporter / Kafka exporter (remove the new containers + scrape jobs):**
   ```bash
   docker compose rm -sf postgres-exporter kafka-exporter
   # then revert docker-compose.yml (remove the two service blocks)
   # and prometheus/prometheus.yml (remove the two scrape jobs)
   docker compose restart prometheus
   ```

2. **pg_stat_statements (revert shared_preload_libraries):**
   ```bash
   docker exec diep-timescaledb psql -U diep -d diep -tAc \
     "ALTER SYSTEM SET shared_preload_libraries = 'timescaledb';"
   docker exec diep-timescaledb psql -U diep -d diep -tAc \
     "DROP EXTENSION IF EXISTS pg_stat_statements;"
   docker compose restart timescaledb
   ```
   (If this ever crash-loops again with a malformed `postgresql.auto.conf`, fix it via
   a throwaway container mounting `diep-lab_timescale-data` and editing
   `postgresql.auto.conf` directly, as described in §2.)

3. **Alertmanager routing/receivers:**
   ```bash
   git diff alertmanager/alertmanager.yml   # review
   git checkout -- alertmanager/alertmanager.yml   # restore prior (empty) config
   docker compose restart alertmanager
   ```

4. **New alert rules (KafkaOutage, DatabaseOutage):**
   ```bash
   git checkout -- prometheus/alerts.yml
   docker compose restart prometheus
   ```

5. **Grafana dashboards:** delete the two new JSON files from
   `grafana/provisioning/dashboards/` — Grafana's provisioner will remove them from
   the UI on next reload (`disableDeletion: false`).

No application data, audit trail, or business-logic config is touched by any of the
above; rollback does not require restarting `fastapi`, `dispatcher`, `ingestor`,
`portal`, `mqtt`, `redis`, or `kafka`.

---

## 5. Remaining Risks / Findings

| Severity | Finding | Recommendation |
|---|---|---|
| **High** | Alertmanager receivers point to placeholder `*.invalid` webhook URLs — alerts will fire and route correctly but **no human will be notified** in the current state. | Before production, replace the three `webhook_configs.url` values in `alertmanager/alertmanager.yml` with real Slack/PagerDuty/Opsgenie/email endpoints. Consider injecting these via a templating step rather than committing real webhook URLs to the repo. |
| **Medium** | `postgres-exporter`'s `DATA_SOURCE_NAME` embeds `${DB_USER}`/`${DB_PASSWORD}` and is visible via `docker inspect` / container env. | Same exposure class as other DB-credentialed services already in the stack; no new exposure introduced, but worth addressing alongside the Phase 15A "rotate `DB_PASSWORD`" follow-up. |
| **Medium** | `kafka-exporter` connects via the internal `PLAINTEXT://9092` listener (unauthenticated), not the SASL `9094` listener used by application services. | Acceptable for an internal-network-only exporter; if Kafka's PLAINTEXT listener is ever removed/hardened, `kafka-exporter` will need `--sasl.*` flags pointed at `9094`. |
| **Low** | `pg_stat_statements_top` reports only the top 10 queries by total exec time, truncated to 80 chars — adequate for dashboarding but not a full audit log. | If deeper query analysis is needed, query `pg_stat_statements` directly via psql. |
| **Low** | `docker-compose-alertmanager.yml` is a pre-existing unused overlay duplicating the `alertmanager` service already defined in `docker-compose.yml` (not modified this phase). | Candidate for removal in a future cleanup pass — out of scope here per "do not remove containers" guidance, and it's not part of the active compose file. |
| **Carried over from 15A** | `.env` (with rotated secrets) staged in git; `DB_PASSWORD` and `DIEP_*_PASSWORD` values still defaults. | Unchanged — see `PHASE15A_SECURITY_HARDENING_REPORT.md`. |

---

## 6. Readiness Update

| Area | Before 15B | After 15B |
|---|---|---|
| Database observability | None (no exporter) | Connections, size, tx rate, query performance (pg_stat_statements), hypertable + compression stats — dashboarded + alertable |
| Kafka observability | None (no exporter) | Broker health, topic throughput, consumer lag/offsets — dashboarded + alertable |
| Alert routing | Single empty receiver, no severity routing | Severity-based routing tree (critical/warning/default) with inhibition rule, validated end-to-end |
| Outage coverage | MQTT, FastAPI (Grafana absent in 9090's existing) | + Kafka, + Database (TimescaleDB/Postgres) |
| Grafana datasources | 1 (Prometheus), no orphans | unchanged — confirmed clean |

**Estimated readiness: ~85/100** (up from ~80/100), gated mainly on the High finding
above (real Alertmanager notification endpoints) before production cutover.
