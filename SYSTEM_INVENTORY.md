# DIEP System Inventory (v1.0 Pilot Baseline)

**Date:** 2026-06-13
**Scope:** Point-in-time inventory of the running lab stack (`~/projects/diep-lab`,
single-host `docker compose`). Documentation only — captured via `docker compose ps`,
`docker images`, and configuration file inspection; nothing was modified.

---

## 1. Services / containers

25 containers, all on the `diep-net` bridge network.

| Container | Image | Role / tier |
|---|---|---|
| `diep-mqtt` | `eclipse-mosquitto` | Messaging — MQTT broker (mTLS) |
| `diep-kafka` | `apache/kafka:latest` (v4.2.0, KRaft mode) | Messaging — command/event bus |
| `diep-kafka-ui` | `provectuslabs/kafka-ui:latest` | Messaging — topic/consumer-group UI |
| `diep-kafka-exporter` | `danielqsj/kafka-exporter` | Observability — Kafka metrics |
| `diep-ingestor` | `python:3.12` (`ingestor/`) | Application — telemetry ingestor (MQTT→Kafka→TimescaleDB) |
| `diep-dispatcher` | `python:3.12` (`dispatcher/`) | Application — command dispatcher (Kafka→MQTT) |
| `diep-fastapi` | `python:3.12` (`fastapi/`) | Application — REST API |
| `diep-portal` | `node:20` (`portal/`, Next.js 14.2.5) | Application — Operator Portal |
| `diep-nodered` | `nodered/node-red` | Application — flow orchestration / device simulation |
| `diep-timescaledb` | `timescale/timescaledb:latest-pg16` | Data — primary database (Postgres 16 + TimescaleDB) |
| `diep-redis` | `redis:7-alpine` | Data — cache / state store |
| `diep-minio` | `minio/minio` | Data — S3-compatible object store (backups) |
| `diep-influxdb` | `influxdb:1.8` | Data — orphaned, no active Grafana datasource (candidate for removal) |
| `diep-grafana` | `grafana/grafana` | Observability — dashboards |
| `diep-prometheus` | `prom/prometheus` | Observability — metrics store / alert rules |
| `diep-alertmanager` | `prom/alertmanager` | Observability — alert routing (no receiver configured) |
| `diep-node-exporter` | `prom/node-exporter` | Observability — host metrics |
| `diep-postgres-exporter` | `quay.io/prometheuscommunity/postgres-exporter` | Observability — Postgres metrics |
| `diep-cadvisor` | `gcr.io/cadvisor/cadvisor:latest` (privileged) | Observability — per-container resource metrics |
| `diep-battery-edge` | `python:3.12` (`drivers/battery/`) | Edge — battery (CAN/BMS) adapter, device `BAT001` |
| `diep-ev-charger` | `python:3.12` (`drivers/ev_charger/`, OCPP) | Edge — EV charger adapter, device `EV001` |
| `diep-sunspec-edge` | `python:3.12` (`drivers/sunspec/`) | Edge — solar inverter (SunSpec/Modbus) adapter, device `INV001` |
| `diep-microgrid-edge` | `python:3.12` (`drivers/microgrid/`) | Edge — microgrid controller adapter, device `MG001` |
| `diep-meter-edge` | `python:3.12` (`drivers/meter/`) | Edge — smart meter adapter, device `METER001` |

**Profile/overlay-only compose files (not part of the default 25-container stack):**
`docker-compose-ha.yml` (Caddy LB seam + `diep-fastapi-2` + Redis replica),
`docker-compose-vault.yml` (HashiCorp Vault), plus per-device single-service compose
files (`docker-compose-battery.yml`, `-microgrid.yml`, `-solar.yml`, etc.) used for
ad-hoc device testing.

---

## 2. Port inventory

| Port | Container | Protocol | Exposure |
|---|---|---|---|
| 8883 | `diep-mqtt` | MQTT over mTLS | Should be exposed to site edge gateways |
| 1883, 9001 | `diep-mqtt` | Plaintext MQTT / WebSocket (listeners disabled in `mosquitto.conf`) | **Dead mapping** — listener commented out (Phase 9J-S4); remove from compose |
| 8000 | `diep-fastapi` | HTTP (REST API) | Operator-facing — needs TLS reverse proxy before exposure |
| 3002 | `diep-portal` | HTTP (Next.js, mapped from container :3000) | Operator-facing — needs TLS reverse proxy |
| 3001 | `diep-grafana` | HTTP (mapped from container :3000) | Ops-facing — needs TLS reverse proxy |
| 9090 | `diep-prometheus` | HTTP | Internal/ops VLAN only |
| 9093 | `diep-alertmanager` | HTTP | Internal/ops VLAN only |
| 9100 | `diep-node-exporter` | HTTP | Internal/ops VLAN only |
| 9187 | `diep-postgres-exporter` | HTTP | Internal/ops VLAN only |
| 9308 | `diep-kafka-exporter` | HTTP | Internal/ops VLAN only |
| 8080 | `diep-cadvisor` | HTTP | Internal/ops VLAN only |
| 8081 | `diep-kafka-ui` | HTTP (mapped from container :8080) | Internal only |
| 5432 | `diep-timescaledb` | Postgres wire protocol | Internal only — must not be exposed beyond `127.0.0.1`/`diep-net` |
| 6379 | `diep-redis` | Redis wire protocol (`requirepass`) | Internal only |
| 9092 | `diep-kafka` | Kafka PLAINTEXT (internal listener) | Internal only |
| 9094 | `diep-kafka` | Kafka SASL_PLAINTEXT (additive, Phase 9J-S5) | Internal only; SASL_SSL recommended before WAN exposure |
| 9000, 9002 | `diep-minio` | S3 API / Console (mapped from container :9000/:9001) | Internal only |
| 8086 | `diep-influxdb` | InfluxDB HTTP API | Internal only — orphaned service |
| 1880 | `diep-nodered` | HTTP (flow editor) | Internal only |

---

## 3. Databases

| Item | Detail |
|---|---|
| Engine | TimescaleDB (Postgres 16), container `diep-timescaledb` |
| Database name | `diep` (configured via `DB_NAME`) |
| Tables (14) | `tenants`, `sites`, `devices`, `telemetry` (hypertable), `commands`, `derms_requests`, `alarms`, `analytics_events`, `audit_events`, `battery_assets`, `ev_chargers`, `solar_assets`, `device_onboarding`, `device_certifications` |
| Continuous aggregates | `telemetry_1m`, `telemetry_1h` (per Phase 9 schema report) |
| Retention / compression | 90-day retention, compression after 7 days (per `DIEP_PHASE9SCHEMA_REPORT.md`) |
| Cache / state store | Redis 7 (`diep-redis`), `requirepass` enabled (Phase 15A), keys `state:<DEVICE_ID>`, `command:<COMMAND_ID>` |
| Object store | MinIO (`diep-minio`), buckets `diep-db-backups`, `diep-config-backups` |
| Orphaned store | InfluxDB 1.8 (`diep-influxdb`) — no Grafana datasource, no known writer |

---

## 4. Message brokers

| Item | Detail |
|---|---|
| MQTT broker | Eclipse Mosquitto, mTLS-only on :8883 (`allow_anonymous false`, `use_identity_as_username`); plaintext 1883/9001 listeners disabled |
| Kafka | `apache/kafka:latest` (v4.2.0), KRaft single-broker mode |
| Kafka listeners | PLAINTEXT :9092 (internal), SASL_PLAINTEXT :9094 (additive, Phase 9J-S5) |
| Kafka topics (observed) | `diep.commands`, `__consumer_offsets` |
| Kafka UI | `provectuslabs/kafka-ui` on :8081 for topic/consumer-group inspection |

---

## 5. Certificates

CA-issued mTLS certificates under `certs/devices/` (Phase 9J-S4):

| Artifact | File(s) |
|---|---|
| CA certificate | `ca.crt` |
| Broker server cert/key | `mosquitto/config/certs/server.crt` / `server.key` |
| Device client certs | `BAT001`, `BAT900`, `EV001`, `INV001`, `INV900`, `MG001`, `MGC900`, `MTR900`, `METER001` (`.crt`/`.key` pairs) |
| Service client certs | `ingestor`, `dispatcher`, `csms` (`.crt`/`.key` pairs) |

Operator-facing TLS (Portal/Grafana/API) is **not yet provisioned** — Caddy reverse-proxy
seam exists (`caddy/Caddyfile`, Phase 9J-S6/9K) but is not active in the default stack.

---

## 6. Secrets locations

| Secret | Variable | Location | Rotation status (Phase 15A) |
|---|---|---|---|
| Database password | `DB_PASSWORD` | `.env` | ✅ Rotated |
| JWT signing secret | `DIEP_JWT_SECRET` | `.env` | ✅ Rotated |
| Admin API key | `DIEP_ADMIN_KEY` | `.env` | ✅ Rotated |
| Operator API key | `DIEP_OPERATOR_KEY` | `.env` | ✅ Rotated |
| Service token | `DIEP_SERVICE_TOKEN` | `.env` | ✅ Rotated |
| Portal token | `DIEP_PORTAL_TOKEN` | `.env` | ✅ Rotated |
| MQTT broker password | `MQTT_PASS` | `.env` / `mosquitto/config/passwd` | ✅ Rotated |
| Redis auth | `REDIS_PASSWORD` | `.env` | ✅ Rotated |
| MinIO root credentials | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `.env` | ✅ Rotated |
| Admin login password | `DIEP_ADMIN_PASSWORD` | `.env` | ❌ Default (`change-me-*`) — **rotate before go-live** |
| Operator login password | `DIEP_OPERATOR_PASSWORD` | `.env` | ❌ Default — **rotate before go-live** |
| Viewer login password | `DIEP_VIEWER_PASSWORD` | `.env` | ❌ Default — **rotate before go-live** |
| Acme tenant password | `DIEP_ACME_PASSWORD` | Referenced in `PHASE15A_SECURITY_HARDENING_REPORT.md`; not present in current `.env`/`.env.example` — locate in tenant-onboarding config before go-live | ❌ Default |
| Globex tenant password | `DIEP_GLOBEX_PASSWORD` | Same as above | ❌ Default |
| Per-device mTLS keys | n/a | `certs/devices/*.key` | N/A — issued, not "rotated"; plan a 1-year rotation cadence |

`.env` is excluded from configuration backups (`scripts/backup-config.sh`) — restore
secrets from a secrets vault/manager separately during disaster recovery.

---

## 7. Volumes

| Volume | Used by | Contents |
|---|---|---|
| `timescale-data` | `diep-timescaledb` | Postgres/TimescaleDB data directory |
| `kafka-data` | `diep-kafka` | Kafka log segments + checkpoint files |
| `redis-data` | `diep-redis` | Redis RDB/AOF persistence |
| `minio-data` | `diep-minio` | Backup objects (`diep-db-backups`, `diep-config-backups`) |
| `grafana-data` | `diep-grafana` | Dashboards, datasources, users |
| `prometheus-data` | `diep-prometheus` | TSDB metrics storage |
| `influxdb-data` | `diep-influxdb` | Orphaned InfluxDB data |

---

## 8. Cross-references

- Architecture detail: [`DIEP_DEPLOYMENT_ARCHITECTURE.md`](DIEP_DEPLOYMENT_ARCHITECTURE.md)
- Configuration detail: [`CONFIGURATION_BASELINE.md`](CONFIGURATION_BASELINE.md)
- Versions/BOM: [`DEPLOYMENT_BOM.md`](DEPLOYMENT_BOM.md)
