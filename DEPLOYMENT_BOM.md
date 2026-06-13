# DIEP Deployment Bill of Materials (v1.0 Pilot Baseline)

**Date:** 2026-06-13
**Scope:** Software, image, and dependency versions for the v1.0 pilot baseline, as
observed on the running lab host. Documentation only.

---

## 1. Host OS

| Item | Version |
|---|---|
| OS | Ubuntu 26.04 LTS |
| Kernel | Linux 7.0.0-22-generic |
| Docker Engine | ≥ 24.x with Compose V2 (`docker compose` plugin) |

See [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md) §3 for full OS package
requirements.

---

## 2. Container images and versions

Versions/digests below were captured live from the running stack
(`docker images` / in-container `--version`). Images marked **floating tag** use
`latest` or `latest-pg16` in `docker-compose.yml` — the digest is the version resolved
at this baseline's last pull, but a future `docker compose pull` may silently change it.

| Service | Image:tag | Resolved version | Tag type |
|---|---|---|---|
| `diep-mqtt` | `eclipse-mosquitto:latest` | Mosquitto 2.1.2 | Floating |
| `diep-kafka` | `apache/kafka:latest` | Kafka 4.2.0 (KRaft) | Floating |
| `diep-kafka-ui` | `provectuslabs/kafka-ui:latest` | image built 2024-04-10 | Floating |
| `diep-kafka-exporter` | `danielqsj/kafka-exporter:latest` | image built 2026-04-13 | Floating |
| `diep-timescaledb` | `timescale/timescaledb:latest-pg16` | PostgreSQL 16.14 + TimescaleDB | Floating |
| `diep-redis` | `redis:7-alpine` | Redis 7.4.9 | Pinned major (7), floating patch |
| `diep-minio` | `minio/minio:latest` | image built 2025-09-07 | Floating |
| `diep-influxdb` | `influxdb:1.8` | InfluxDB 1.8 | Pinned (orphaned service) |
| `diep-grafana` | `grafana/grafana:latest` | image built 2026-06-02 | Floating |
| `diep-prometheus` | `prom/prometheus:latest` | Prometheus 3.12.0 | Floating |
| `diep-alertmanager` | `prom/alertmanager:latest` | Alertmanager 0.32.2 | Floating |
| `diep-node-exporter` | `prom/node-exporter:latest` | image built 2026-04-07 | Floating |
| `diep-postgres-exporter` | `quay.io/prometheuscommunity/postgres-exporter:latest` | image built 2026-02-25 | Floating |
| `diep-cadvisor` | `gcr.io/cadvisor/cadvisor:latest` | image built 2025-12-25 | Floating |
| `diep-nodered` | `nodered/node-red:latest` | Node-RED 5.0.0 / Node.js 24.16.0 | Floating |
| `diep-portal` | `node:20` | Node 20.x + Next.js 14.2.5, React 18.3.1 | Pinned major (20) |
| `diep-fastapi`, `diep-ingestor`, `diep-dispatcher`, edge adapters (`diep-battery-edge`, `diep-ev-charger`, `diep-sunspec-edge`, `diep-microgrid-edge`, `diep-meter-edge`) | `python:3.12` | Python 3.12 | Pinned major.minor |

**Image digests** (for the floating-tag images, pinned to the digest observed at this
baseline; record/compare on future pulls):

| Image:tag | Digest |
|---|---|
| `apache/kafka:latest` | `sha256:9516fb7634bad307d17c33b589fde9023003b0cb761374f500002b980a3149b9` |
| `eclipse-mosquitto:latest` | `sha256:a908c65cc8e67ec9d292ef27c2c0360dbaaee7eb1b935cdd194e67697f15dea1` |
| `timescale/timescaledb:latest-pg16` | `sha256:51ac20ec295699c05573adf896e2449d8b3a026223a951905d5763687409d7d4` |
| `grafana/grafana:latest` | `sha256:5dad0df181cb644a14e13617b913b261a54f7d4fd4510721dba420929f35bea2` |
| `prom/prometheus:latest` | `sha256:69f5241418838263316593f7274a304b095c40bcf22e57272865da91bd60a8ac` |
| `prom/alertmanager:latest` | `sha256:b85533a2eb45865835315810315f6951331b2dbc8c93a6cf9a51e156a006a706` |
| `prom/node-exporter:latest` | `sha256:e9cff4fc67b1818f8c97adb115b9f12c9a54b533de86765d4a0effc01b357205` |
| `quay.io/prometheuscommunity/postgres-exporter:latest` | `sha256:e96064f876226d94bb6ce48a4c4b3dd76edba91168ec1ab024e5c4b959310b0f` |
| `danielqsj/kafka-exporter:latest` | `sha256:a51b280b55a763deaa1bc5024310bc2954995d9160014d7445055dac6a090868` |
| `gcr.io/cadvisor/cadvisor:latest` | `sha256:3de2bd5203120b866d74a9b283b2ffb8ec382fbf9dc321814700c6ea6f44ec57` |
| `minio/minio:latest` | `sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e` |
| `provectuslabs/kafka-ui:latest` | `sha256:8f2ff02d64b0a7a2b71b6b3b3148b85f66d00ec20ad40c30bdcd415d46d31818` |
| `nodered/node-red:latest` | `sha256:153f411d2993abd9ccd8290017ff2bb531326320b5cd3b200c1a4bb1339eb819` |

**Recommendation (Known Limitation #10):** before broader rollout, replace floating
`latest`/`latest-pg16` tags in `docker-compose.yml` with explicit version tags matching
the resolved versions above, to prevent unintended upgrades on a future
`docker compose pull` / image rebuild.

---

## 3. Application dependencies

### 3.1 FastAPI (`fastapi/requirements.txt`, Phase 10A pinned)

| Package | Version |
|---|---|
| `fastapi` | 0.136.3 |
| `uvicorn[standard]` | 0.49.0 |
| `pydantic` | 2.13.4 |
| `psycopg2-binary` | 2.9.12 |
| `kafka-python` | 2.3.2 |
| `redis` | 8.0.0 |
| `prometheus_client` | 0.25.0 |

### 3.2 Portal (`portal/package.json`)

| Package | Version |
|---|---|
| `next` | 14.2.5 |
| `react` | 18.3.1 |
| Runtime | Node.js 20 (container `node:20`) |

### 3.3 Ingestor / Dispatcher / Edge adapters

Run on `python:3.12`; dependency pins follow the same `requirements.txt` convention as
FastAPI (`kafka-python`, `psycopg2-binary`, MQTT client, protocol-specific libraries per
adapter — see `drivers/<protocol>/requirements.txt`).

---

## 4. Kafka / messaging runtime

| Item | Version |
|---|---|
| Kafka | 4.2.0 (KRaft mode, single broker) |
| Mosquitto | 2.1.2 |
| Node-RED | 5.0.0 (Node.js 24.16.0) |

---

## 5. Data layer runtime

| Item | Version |
|---|---|
| TimescaleDB / PostgreSQL | PostgreSQL 16.14 (Alpine-based image) |
| Redis | 7.4.9 |
| MinIO | image built 2025-09-07 (`RELEASE` tag floating) |
| InfluxDB (orphaned) | 1.8 |

---

## 6. Observability runtime

| Item | Version |
|---|---|
| Prometheus | 3.12.0 |
| Alertmanager | 0.32.2 |
| Grafana | image built 2026-06-02 (latest at baseline) |
| cAdvisor | image built 2025-12-25 |
| node-exporter | image built 2026-04-07 |
| postgres-exporter | image built 2026-02-25 |
| kafka-exporter | image built 2026-04-13 |

---

## 7. Cross-references

- [`SYSTEM_INVENTORY.md`](SYSTEM_INVENTORY.md) — services, ports, databases
- [`CONFIGURATION_BASELINE.md`](CONFIGURATION_BASELINE.md) — compose files, env vars
- [`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md) — OS/Docker requirements
