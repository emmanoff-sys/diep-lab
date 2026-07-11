# Service Health Summary
### RE-OS Development Platform | Post-Recovery Verification
### Verified: 2026-07-11T02:10:00Z

---

## Summary Status: GREEN

All core platform services operational. One service (Prometheus) required manual restart
after clean graceful exit during recovery event. All other services self-recovered.

---

## Service Health Matrix

| Service | Container | Version | Status | Health | Restarts | Notes |
|---------|-----------|---------|--------|--------|----------|-------|
| **FastAPI** | diep-fastapi | Python 3.12 | Running | ✅ GREEN | 0 | /healthz 200 continuous |
| **TimescaleDB** | diep-timescaledb | PG 16.14 / TS 2.28.0 | Running | ✅ GREEN | 0 | CAgg + checkpoint active |
| **Kafka** | diep-kafka | Apache Kafka (latest) | Running | ✅ GREEN | 0 | 0 consumer lag, KRaft |
| **Redis Master** | diep-redis | 7.4.9 | Running | ✅ GREEN | 0 | Master role confirmed |
| **Redis Replica** | diep-redis-replica | 7.4.9 | Running | ✅ GREEN | 0 | Synced, lag ~1s |
| **Redis Sentinel 1** | diep-redis-sentinel-1 | 7.4.9 | Running | ✅ GREEN | 0 | Quorum 2 |
| **Redis Sentinel 2** | diep-redis-sentinel-2 | 7.4.9 | Running | ✅ GREEN | 0 | — |
| **Redis Sentinel 3** | diep-redis-sentinel-3 | 7.4.9 | Running | ✅ GREEN | 0 | — |
| **Grafana** | diep-grafana | 13.1.0 | Running | ✅ GREEN | 0 | INFO-only logs |
| **Prometheus** | diep-prometheus | — | Running | ✅ GREEN | 0 | Restarted at 01:48Z |
| **AlertManager** | diep-alertmanager | — | Running | ✅ GREEN | 0 | — |
| **MinIO** | diep-minio | — | Running | ✅ GREEN | 0 | WAL archive healthy |
| **WAL Shipper** | diep-wal-shipper | mc | Running | ✅ GREEN | 0 | 1 segment/min to MinIO |
| **Node Exporter** | diep-node-exporter | — | Running | ✅ GREEN | 0 | Metrics active |
| **Postgres Exporter** | diep-postgres-exporter | — | Running | ✅ GREEN | 0 | — |
| **Redis Exporter** | diep-redis-exporter | — | Running | ✅ GREEN | 0 | — |
| **Kafka Exporter** | diep-kafka-exporter | 1.9.0 | Running | ⚠️ STABLE | 11 | Transient startup race; stable |
| **Node-RED** | diep-nodered | — | Running | ✅ GREEN | 0 | Healthy (container label) |
| **OMS Detector** | diep-oms-detector | Python 3.12 | Running | ✅ GREEN | 0 | Healthy (container label) |
| **Dispatcher** | diep-dispatcher | Python 3.12 | Running | ⚠️ STABLE | 1 | 1 startup restart; stable |
| **Ingestor** | diep-ingestor | Python 3.12 | Running | ✅ GREEN | 0 | — |
| **EV Charger** | diep-ev-charger | Python 3.12 | Running | ✅ GREEN | 0 | — |
| **Caddy** | diep-caddy | 2-alpine | Running | ✅ GREEN | 0 | Reverse proxy |
| **MQTT** | diep-mqtt | eclipse-mosquitto | Running | ✅ GREEN | 0 | — |
| **InfluxDB** | diep-influxdb | 1.8 | Running | ✅ GREEN | 0 | — |
| **Portal** | diep-portal | node:20 | Running | ✅ GREEN | 0 | — |

---

## Prometheus Scrape Target Health

| Target Job | Health | Note |
|-----------|--------|------|
| diep-fastapi | UP | — |
| kafka-exporter | UP | — |
| minio | UP | — |
| node-exporter | UP | — |
| postgres-exporter | UP | — |
| prometheus (self) | UP | — |
| redis-exporter | UP | — |
| cadvisor | DOWN | Not deployed in dev env (expected) |
| diep-mdm | DOWN | Not deployed in dev env (expected) |
| diep-opcua-connector | DOWN | Not deployed in dev env (expected) |

---

## Key Metrics (T+0)

| Metric | Value |
|--------|-------|
| WAL LSN | `F/C4000490` |
| WAL archive last segment | `000000010000000F000000CA` (01:48:46Z) |
| WAL shipping cadence | ~60 seconds |
| Kafka consumer lag | 0 |
| Redis master offset | 2,544,986 |
| Redis replica offset | 2,544,839 (lag ~1s) |
| TimescaleDB checkpoint distance | 81,920 KiB (~80 MiB) |
| FastAPI uptime | 3+ hours |

---

*Produced: 2026-07-11T02:10:00Z*
