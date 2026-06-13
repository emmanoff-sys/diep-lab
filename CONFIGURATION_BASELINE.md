# DIEP Configuration Baseline (v1.0 Pilot Baseline)

**Date:** 2026-06-13
**Scope:** Snapshot of the configuration that produces the running v1.0 pilot stack.
Documentation only — no configuration files were changed to produce this document.

---

## 1. Docker Compose files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Primary stack — all 25 default services (messaging, application, data, observability, edge adapters) |
| `docker-compose-ha.yml` | Optional HA overlay — Caddy LB/TLS seam, `diep-fastapi-2` second API replica, Redis replica (live-verified, not default) |
| `docker-compose-vault.yml` | Optional — HashiCorp Vault for future secrets management |
| `docker-compose-fastapi.yml`, `-ingestor.yml`, `-portal.yml`, `-minio.yml`, `-redis.yml`, `-timescale.yml`, `-alertmanager.yml`, `-cadvisor.yml`, `-kafka-ui.yml` | Per-service standalone definitions (used for targeted rebuilds / partial `-f` chaining) |
| `docker-compose-battery.yml`, `-battery-edge.yml`, `-ev-charger.yml`, `-meter.yml`, `-microgrid.yml`, `-microgrid-edge.yml`, `-solar.yml`, `-sunspec.yml`, `-ocpp.yml` | Per-device edge adapter / simulator definitions |

**Startup composition:** `./start-all-diep.sh` runs `docker compose up -d` against
`docker-compose.yml` only (the 25-service default stack), then applies `init-db.sh` and
Node-RED flow deployment. Overlay files are opt-in via explicit `-f` chaining
(`docker compose -f docker-compose.yml -f docker-compose-ha.yml up -d`).

---

## 2. Environment variables (`.env`, from `.env.example`)

All names below are defined in `.env.example` as placeholders; actual values live only
in `.env` (excluded from config backups and from this document).

| Variable | Purpose | Rotation status |
|---|---|---|
| `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | TimescaleDB connection | `DB_PASSWORD` ✅ rotated (Phase 15A) |
| `DIEP_AUTH_ENFORCED` | Gates API auth enforcement (`1` = enforced) | n/a (flag) |
| `DIEP_JWT_SECRET`, `DIEP_JWT_TTL` | JWT signing secret / token TTL | `DIEP_JWT_SECRET` ✅ rotated |
| `DIEP_ADMIN_USER`, `DIEP_ADMIN_KEY`, `DIEP_ADMIN_PASSWORD` | Admin role credentials | `DIEP_ADMIN_KEY` ✅ rotated; `DIEP_ADMIN_PASSWORD` ❌ default |
| `DIEP_OPERATOR_KEY`, `DIEP_OPERATOR_PASSWORD` | Operator role credentials | `DIEP_OPERATOR_KEY` ✅ rotated; `DIEP_OPERATOR_PASSWORD` ❌ default |
| `DIEP_VIEWER_PASSWORD` | Viewer role login password | ❌ default |
| `DIEP_SERVICE_TOKEN` | Service-to-service auth token | ✅ rotated |
| `DIEP_PORTAL_TOKEN` | Portal backend auth token | ✅ rotated |
| `MQTT_USER`, `MQTT_PASS` | Mosquitto broker auth (legacy username/password path; mTLS is primary auth) | `MQTT_PASS` ✅ rotated |
| `REDIS_PASSWORD` | Redis `requirepass` | ✅ rotated |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | MinIO root credentials | ✅ rotated |

**Not present in current `.env`/`.env.example`** but referenced as unrotated in
`PHASE15A_SECURITY_HARDENING_REPORT.md`: `DIEP_ACME_PASSWORD`, `DIEP_GLOBEX_PASSWORD`
(tenant-specific demo credentials, Phase 12-14 commercial features) — locate and rotate
in the tenant-onboarding configuration before go-live.

---

## 3. Backup schedules

Installed via `scripts/install-backup-cron.sh` (Phase 15C):

| Time | Job | Script | Output |
|---|---|---|---|
| 02:00 daily | Database backup (`pg_dump` custom format + checksum) | `scripts/backup-db.sh` | `backups/`, MinIO bucket `diep-db-backups` |
| 02:30 daily | Configuration backup (compose files, MQTT certs/config, Alertmanager, Grafana provisioning, Prometheus config; `.env` excluded) | `scripts/backup-config.sh` | `backups/config/`, MinIO bucket `diep-config-backups` |
| 03:00 Sunday | Backup verification (checksum + restore-into-scratch-DB drill) | `scripts/verify-backup.sh` | `backups/logs/verify-backup.log` |

Retention: `BACKUP_RETENTION_DAYS` (default 14), applied via `mc rm --force --older-than`
to both local archives and MinIO buckets. Backups are **unencrypted** at rest (Known
Limitation #9).

---

## 4. Monitoring configuration

### 4.1 Prometheus scrape jobs (`prometheus/prometheus.yml`)

| Job | Target |
|---|---|
| `prometheus` | self |
| `node-exporter` | host metrics (`diep-node-exporter:9100`) |
| `cadvisor` | per-container metrics (`diep-cadvisor:8080`) |
| `diep-fastapi` | `/metrics` on `diep-fastapi:8000` |
| `postgres-exporter` | `diep-postgres-exporter:9187` |
| `kafka-exporter` | `diep-kafka-exporter:9308` |

### 4.2 Alert rules (`prometheus/alerts.yml`)

10 rules: `DiepApiDown`, `DatabaseOutage`, `KafkaOutage`, `MQTTDown`, `GrafanaDown`,
`HighCPUUsage`, `HighMemoryUsage`, `PrometheusDown`, `NodeExporterDown`, `CadvisorDown`.

### 4.3 Alertmanager routing (`alertmanager/alertmanager.yml`)

- Route tree groups by `alertname`/`severity`, with dedicated `critical` (1h repeat) and
  `warning` routes, default `group_wait=30s`, `group_interval=5m`, `repeat_interval=4h`.
- An inhibition rule suppresses `HighCommandFailureRate` while `DiepApiDown` is firing.
- **All three receivers (`default`, `critical`, `warning`) point to placeholder
  `*.invalid` webhook URLs** — alerts are routed and grouped correctly but produce **no
  real external notification**. Phase 15B left `.env.example` placeholders
  (`DIEP_ALERT_*_WEBHOOK_URL`) for wiring real Slack/PagerDuty/Opsgenie endpoints. This
  matches Known Limitation #5 and is a pre-go-live action item.

### 4.4 Grafana provisioning (`grafana/provisioning/`)

| File | Purpose |
|---|---|
| `datasources/prometheus.yml` | Prometheus datasource (default) |
| `dashboards/dashboards.yml` | Dashboard provider config |
| `dashboards/command-path.json` | Command lifecycle (PENDING→SENT→ACKED) dashboard |
| `dashboards/kafka.json` | Kafka broker/topic metrics dashboard |
| `dashboards/postgres-timescaledb.json` | TimescaleDB metrics dashboard |

No InfluxDB datasource is provisioned — consistent with `diep-influxdb` being orphaned
(Known Limitation #7).

---

## 5. Cross-references

- Procedures using this configuration: [`DIEP_OPERATIONS_MANUAL.md`](DIEP_OPERATIONS_MANUAL.md)
- Full inventory: [`SYSTEM_INVENTORY.md`](SYSTEM_INVENTORY.md)
- Versions: [`DEPLOYMENT_BOM.md`](DEPLOYMENT_BOM.md)
