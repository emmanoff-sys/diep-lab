# DIEP Deployment Architecture (Phase 16, Task 1)

**Date:** 2026-06-13
**Scope:** Pilot deployment architecture — logical, physical, network, and security views —
for the DIEP platform as it exists today (single-host `docker compose` lab, 25 containers,
readiness ≈ 88/100 after Phases 15A/15B/15C). Documentation only; no code, configuration,
or running services were changed to produce this document.

Diagram sources:
- [`diagrams/01_logical_architecture.mmd`](diagrams/01_logical_architecture.mmd)
- [`diagrams/02_physical_architecture.mmd`](diagrams/02_physical_architecture.mmd)
- [`diagrams/03_network_architecture.mmd`](diagrams/03_network_architecture.mmd)
- [`diagrams/04_security_architecture.mmd`](diagrams/04_security_architecture.mmd)
- [`diagrams/diep_deployment_architecture.drawio`](diagrams/diep_deployment_architecture.drawio) — physical deployment, open in [diagrams.net](https://app.diagrams.net) (File → Open from Device)

---

## 1. Logical architecture

DIEP is a layered telemetry/command pipeline: field devices → edge protocol adapters →
MQTT (mTLS) → ingestor/dispatcher → Kafka → FastAPI → TimescaleDB/Redis, fronted by an
operator portal and Grafana, with Prometheus/Alertmanager for monitoring.

```mermaid
flowchart LR
  subgraph FIELD["Field / Site Devices"]
    MTR["Smart Meter\nMETER001 (Modbus)"]
    INV["Solar Inverter\nINV001 (SunSpec)"]
    BAT["Battery BMS\nBAT001 (CAN/Modbus)"]
    EVC["EV Charger\nEV001 (OCPP)"]
    MG["Microgrid RTU\nMG001 (IEC-104/61850)"]
  end

  subgraph EDGE["Edge Layer"]
    DRV["Protocol Adapters\n(drivers/ SDK, mTLS client identity)"]
  end

  MTR & INV & BAT & EVC & MG -->|local protocols| DRV

  subgraph MSG["Messaging / Ingest"]
    MQTT[("MQTT Broker\nMosquitto, mTLS :8883")]
    ING["Telemetry Ingestor"]
    KAFKA[("Kafka\ntopics: diep.commands, telemetry")]
    DISP["Command Dispatcher"]
  end

  DRV -->|telemetry publish diep/+/+/data| MQTT
  MQTT -->|subscribe| ING
  ING -->|produce| KAFKA
  KAFKA -->|consume diep.commands| DISP
  DISP -->|cmd publish diep/+/+/cmd| MQTT
  MQTT -->|ack publish diep/+/+/ack| DISP

  subgraph APP["Application Tier"]
    API["FastAPI\n/derms /commands /telemetry /auth"]
    PORTAL["Operator Portal (Next.js)"]
  end

  ING -->|REST telemetry POST| API
  API <-->|produce/consume| KAFKA
  PORTAL -->|REST + JWT/API key| API

  subgraph DATA["Data Tier"]
    TSDB[("TimescaleDB\ntelemetry, devices, commands,\nderms_requests, audit_events")]
    REDIS[("Redis\nstate:* cache, command cache")]
    MINIO[("MinIO\nbackup object storage")]
  end

  API <--> TSDB
  API <--> REDIS
  TSDB -.nightly backup.-> MINIO

  subgraph OBS["Observability"]
    PROM["Prometheus"]
    GRAF["Grafana"]
    ALERT["Alertmanager"]
  end

  API -- "/metrics" --> PROM
  TSDB -- postgres_exporter --> PROM
  KAFKA -- kafka_exporter --> PROM
  PROM --> GRAF
  PROM --> ALERT
```

### 1.1 Component summary

| Layer | Components | Purpose |
|---|---|---|
| Field | METER001, INV001, BAT001, EV001, MG001 (+ test variants BAT900/MGC900/etc.) | Physical/simulated DERMS assets |
| Edge | `drivers/` protocol adapter SDK, per-device mTLS client certs (`certs/devices/*`) | Normalize device protocols into MQTT telemetry/cmd/ack topics |
| Messaging | `diep-mqtt` (Mosquitto, mTLS-only on 8883), `diep-kafka` (KRaft, single broker) | Pub/sub transport for telemetry and commands |
| Ingest/Dispatch | `diep-ingestor`, `diep-dispatcher` | Bridge MQTT ↔ Kafka ↔ FastAPI for telemetry and command round-trips |
| Application | `diep-fastapi` (REST API, auth, DERMS logic), `diep-portal` (Next.js operator UI), `diep-nodered` (flow automation) | Business logic, operator UX |
| Data | `diep-timescaledb` (system of record), `diep-redis` (live state cache), `diep-minio` (backup object store) | Persistence and caching |
| Observability | `diep-prometheus`, `diep-grafana`, `diep-alertmanager`, `diep-cadvisor`, `diep-node-exporter`, `diep-postgres-exporter`, `diep-kafka-exporter` | Metrics, dashboards, alerting |

---

## 2. Physical deployment architecture

The current pilot runs as a **single-host `docker compose` stack** (25 containers) on one
Linux VM/host. All containers share one bridge network (`diep-net`) and seven named Docker
volumes for persistent state.

```mermaid
flowchart TB
  subgraph HOST["Pilot Host — Ubuntu 22.04/24.04 LTS (4 vCPU / 8-16 GB RAM / 100+ GB SSD)"]
    direction TB

    subgraph NET["Docker bridge network: diep-net (172.x.0.0/16)"]
      direction LR

      subgraph TIER_EDGE["Edge / device simulators"]
        E1["diep-meter-edge"]
        E2["diep-sunspec-edge"]
        E3["diep-battery-edge"]
        E4["diep-ev-charger"]
        E5["diep-microgrid-edge"]
      end

      subgraph TIER_MSG["Messaging"]
        M1["diep-mqtt\n(mosquitto, :8883 mTLS)"]
        M2["diep-kafka\n(KRaft, :9092/:9094)"]
        M3["diep-kafka-ui\n(:8081)"]
      end

      subgraph TIER_APP["Application"]
        A1["diep-fastapi\n(:8000)"]
        A2["diep-ingestor"]
        A3["diep-dispatcher"]
        A4["diep-portal\n(:3002)"]
        A5["diep-nodered\n(:1880)"]
      end

      subgraph TIER_DATA["Data"]
        D1[("diep-timescaledb\n(:5432)")]
        D2[("diep-redis\n(:6379)")]
        D3[("diep-minio\n(:9000/:9002)")]
        D4[("diep-influxdb\n(:8086, legacy)")]
      end

      subgraph TIER_OBS["Observability"]
        O1["diep-prometheus (:9090)"]
        O2["diep-grafana (:3001)"]
        O3["diep-alertmanager (:9093)"]
        O4["diep-cadvisor (:8080)"]
        O5["diep-node-exporter (:9100)"]
        O6["diep-postgres-exporter (:9187)"]
        O7["diep-kafka-exporter (:9308)"]
      end
    end

    VOL[("Named Docker volumes:\ntimescale-data, kafka-data,\nredis-data, minio-data,\ngrafana-data, prometheus-data,\ninfluxdb-data")]
    CRON["Host crontab\n(02:00 DB backup, 02:30 config backup,\n03:00 Sun verify drill)"]
    BK["./backups/ (local archive)"]
  end

  TIER_DATA --- VOL
  CRON --> BK
  D1 -.pg_dump.-> BK
  BK -.mc cp.-> D3

  OPS["Operator workstation"] -->|HTTPS :3002 portal\nHTTPS :3001 grafana\nHTTPS :8000 api| HOST
  GW["Site edge gateways"] -->|mTLS :8883| HOST
```

### 2.1 Current host profile (live-measured)

| Resource | Total | In use (steady-state, 25 containers) |
|---|---|---|
| CPU | 4 vCPU | ~25-35% aggregate (cAdvisor itself is the heaviest single consumer at ~80% of 1 core) |
| Memory | 7.2 GiB | ~4.8 GiB used (Kafka ~490 MiB, cAdvisor ~740 MiB, Portal ~320 MiB largest consumers) |
| Disk | 48 GB | 26 GB used / 21 GB free |

This profile is adequate for a **pilot with ≤ ~10 simulated/real devices**. See
[`DIEP_INSTALLATION_GUIDE.md`](DIEP_INSTALLATION_GUIDE.md) §1 for sizing recommendations
for a customer pilot (real devices + headroom for compression/retention).

### 2.2 Container inventory by tier

| Tier | Containers |
|---|---|
| Edge/simulators | `diep-meter-edge`, `diep-sunspec-edge`, `diep-battery-edge`, `diep-ev-charger`, `diep-microgrid-edge` |
| Messaging | `diep-mqtt`, `diep-kafka`, `diep-kafka-ui` |
| Application | `diep-fastapi`, `diep-ingestor`, `diep-dispatcher`, `diep-portal`, `diep-nodered` |
| Data | `diep-timescaledb`, `diep-redis`, `diep-minio`, `diep-influxdb` (legacy, no Grafana datasource — see §6) |
| Observability | `diep-prometheus`, `diep-grafana`, `diep-alertmanager`, `diep-cadvisor`, `diep-node-exporter`, `diep-postgres-exporter`, `diep-kafka-exporter` |

---

## 3. Network architecture

```mermaid
flowchart LR
  subgraph ZONE_USER["Untrusted: Operator / User network"]
    BROWSER["Operator browser"]
    MOBILE["Mobile app (Phase 11)"]
  end

  subgraph ZONE_SITE["Untrusted: Site / field networks"]
    GATEWAY["Edge gateway\n(per-device mTLS cert)"]
  end

  subgraph ZONE_DMZ["DMZ — pilot host, exposed ports"]
    PORTAL["Portal :3002 (HTTP→HTTPS via reverse proxy)"]
    GRAFANA["Grafana :3001"]
    API["FastAPI :8000 (JWT / API-key)"]
    MQTT["MQTT :8883 (TLS+mTLS only)"]
    KAFKAUI["Kafka UI :8081 (internal-only, restrict)"]
  end

  subgraph ZONE_CORE["Trusted core — diep-net bridge, no external exposure recommended"]
    KAFKA["Kafka :9092/:9094 SASL"]
    TSDB[("TimescaleDB :5432")]
    REDIS[("Redis :6379 (requirepass)")]
    MINIO[("MinIO :9000/:9002")]
    INGESTOR["Ingestor"]
    DISPATCHER["Dispatcher"]
  end

  subgraph ZONE_MON["Monitoring — internal, restrict to ops VLAN"]
    PROM["Prometheus :9090"]
    ALERT["Alertmanager :9093"]
    EXPORTERS["Exporters\n9100/9187/9308/8080"]
  end

  BROWSER -->|HTTPS 443→3002| PORTAL
  BROWSER -->|HTTPS 443→3001| GRAFANA
  MOBILE -->|HTTPS 443→8000| API
  PORTAL -->|internal| API
  GATEWAY -->|mTLS :8883, CA-signed client cert| MQTT

  MQTT --> INGESTOR --> API
  API <--> TSDB
  API <--> REDIS
  API <--> KAFKA
  DISPATCHER <--> KAFKA
  DISPATCHER --> MQTT
  TSDB -.backup.-> MINIO

  API --> EXPORTERS
  TSDB --> EXPORTERS
  KAFKA --> EXPORTERS
  EXPORTERS --> PROM --> ALERT
  PROM --> GRAFANA

  classDef exposed fill:#fde2e1,stroke:#c0392b;
  classDef internal fill:#e3f2fd,stroke:#1565c0;
  class PORTAL,GRAFANA,API,MQTT exposed;
  class KAFKA,TSDB,REDIS,MINIO,KAFKAUI,PROM,ALERT,EXPORTERS internal;
```

### 3.1 Port inventory (as currently bound in compose files)

| Port | Service | Exposure recommendation for pilot |
|---|---|---|
| 8883/tcp | MQTT (mTLS only, `allow_anonymous false`) | **Expose** to site/edge gateway network only (firewalled to known gateway IPs) |
| 8000/tcp | FastAPI REST API | Expose behind TLS reverse proxy (Caddy/Phase 9J-S6 seam); JWT/API-key enforced |
| 3002/tcp | Operator Portal | Expose behind TLS reverse proxy |
| 3001/tcp | Grafana | Expose behind TLS reverse proxy; restrict to operator/ops VLAN |
| 9093/tcp | Alertmanager | Internal only |
| 9090/tcp | Prometheus | Internal only |
| 9092, 9094/tcp | Kafka (PLAINTEXT internal, SASL_PLAINTEXT app) | **Do not expose externally**; internal `diep-net` only |
| 5432/tcp | TimescaleDB | **Do not expose externally**; internal only |
| 6379/tcp | Redis (requirepass enabled, Phase 15A) | **Do not expose externally**; internal only |
| 9000/9002/tcp | MinIO API/console | Internal only (used by backup scripts) |
| 8081/tcp | Kafka UI | Internal/ops-only — no auth in front of it today |
| 1880/tcp | Node-RED | Internal/ops-only |
| 8086/tcp | InfluxDB (legacy, unused by Grafana) | Internal only; candidate for removal (§6 of Task 5 report) |
| 8080, 9100, 9187, 9308/tcp | cAdvisor, node-exporter, postgres-exporter, kafka-exporter | Internal/ops VLAN only |
| 1883, 9001/tcp | Legacy MQTT plaintext/WS listeners | **Retired since Phase 9J-S4** (commented out in `mosquitto.conf`); the root `docker-compose.yml` still maps these host ports for the `mqtt` service — recommend removing the port mappings before pilot to avoid exposing unused listener ports |

### 3.2 Pilot deployment recommendation

For a customer pilot site:
1. Place the host behind a firewall/NAT; only forward **8883** (device gateways), and
   **443** to a TLS reverse proxy that fronts Portal (3002), Grafana (3001), and the API (8000).
2. All data-tier and messaging-internal ports (5432, 6379, 9000/9002, 9092/9094, 8081)
   stay bound to `127.0.0.1`/the bridge network — never to `0.0.0.0` on a routable interface.
3. Monitoring ports (9090/9093/9100/9187/9308/8080) are reachable only from an
   operations/management VLAN (VPN or jump host).

---

## 4. Security architecture

```mermaid
flowchart TB
  subgraph IDENTITY["Identity & Access"]
    JWT["JWT (DIEP_JWT_SECRET)\n/auth/token, TTL 3600s"]
    APIKEYS["API keys\nDIEP_SERVICE_TOKEN (service)\nDIEP_OPERATOR_KEY (operator)\nDIEP_ADMIN_KEY (admin)"]
    RBAC["Roles: admin / operator / viewer / service\nenforced per-route in fastapi/auth.py"]
  end

  subgraph TRANSPORT["Transport Security"]
    MTLS["MQTT mTLS :8883\nCA-signed per-device certs (certs/devices/*)\nuse_identity_as_username -> ACL by CN"]
    SASL["Kafka SASL_PLAINTEXT :9094\n(PLAIN, diep/diep-kafka-pass)\nrecommend upgrade -> SASL_SSL"]
    TLSPROXY["Phase 9J-S6 seam: Caddy/reverse proxy\nfor portal/Grafana/API TLS termination"]
  end

  subgraph SECRETS["Secrets Management"]
    ENV[".env (gitignored, host-only)\nrotated random secrets (Phase 15A)"]
    BAK[".env.pre-phase15a.bak (rollback copy)"]
    VAULT["docker-compose-vault.yml\n(HashiCorp Vault — available, not yet wired)"]
  end

  subgraph AUDIT["Audit & Monitoring"]
    AUDITTBL["audit_events table\nprincipal, role, action, resource, result, detail"]
    ALERTS["Alertmanager rules\nDiepApiDown, DatabaseOutage,\nHighCommandFailureRate (Phase 15B)"]
  end

  subgraph ACL["MQTT ACLs"]
    ACLFILE["mosquitto/config/acl\nper-CN topic scoping (ingestor/dispatcher/device)"]
  end

  JWT --> RBAC
  APIKEYS --> RBAC
  RBAC --> AUDITTBL
  MTLS --> ACLFILE
  ENV -.consumed by.-> JWT
  ENV -.consumed by.-> APIKEYS
  ENV -.consumed by.-> SASL
  AUDITTBL --> ALERTS
```

### 4.1 Security controls summary

| Control | Status | Notes |
|---|---|---|
| API authentication | ✅ Live | JWT (`/auth/token`) + static API keys (service/operator/admin), `DIEP_AUTH_ENFORCED=1` |
| RBAC | ✅ Live | admin/operator/viewer/service roles enforced per-route |
| MQTT transport security | ✅ Live | mTLS-only on 8883, `allow_anonymous false`, CN-based identity + ACL (Phase 9J-S4) |
| Kafka authentication | ✅ Live (SASL_PLAINTEXT) | recommend SASL_SSL for production (encryption in transit) |
| Redis authentication | ✅ Live | `requirepass` since Phase 15A |
| Secrets rotation | ✅ Done | all placeholder `change-me-*` secrets rotated (Phase 15A); `DIEP_ADMIN_PASSWORD`/`DIEP_OPERATOR_PASSWORD`/`DIEP_VIEWER_PASSWORD`/`DIEP_ACME_PASSWORD`/`DIEP_GLOBEX_PASSWORD` still default — **rotate before customer pilot** |
| Secrets storage | ⚠️ `.env` file on host | Vault compose file exists but not wired; acceptable for single-host pilot with restricted file permissions |
| Audit trail | ✅ Live | `audit_events` table captures command/DERMS actions with principal/role/result; auth events (`/auth/token`, `/auth/whoami`) not yet audited |
| Backup encryption | ⚠️ Not yet | backups stored in MinIO/local archive unencrypted — acceptable in lab, recommend SSE for pilot if backups leave the host |
| TLS for Portal/Grafana/API | ⏳ Seam ready | Caddy reverse-proxy pattern exists (`caddy/Caddyfile`, Phase 9J-S6 seam) but HTTP-only in the lab — **enable TLS termination before exposing to a customer network** |

---

## 5. Cross-references

- HA target architecture and migration stages: [`DIEP_HA_ARCHITECTURE.md`](DIEP_HA_ARCHITECTURE.md)
- Backup/DR procedures: [`PHASE15C_PRODUCTION_OPERATIONS_REPORT.md`](PHASE15C_PRODUCTION_OPERATIONS_REPORT.md)
- Security hardening history: [`PHASE15A_SECURITY_HARDENING_REPORT.md`](PHASE15A_SECURITY_HARDENING_REPORT.md)
- Monitoring hardening: [`PHASE15B_MONITORING_HARDENING_REPORT.md`](PHASE15B_MONITORING_HARDENING_REPORT.md)
- Edge gateway hardware options: [`DIEP_EDGE_GATEWAY_ARCHITECTURE.md`](DIEP_EDGE_GATEWAY_ARCHITECTURE.md)
