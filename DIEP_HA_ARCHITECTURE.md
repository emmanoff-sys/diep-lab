# DIEP High-Availability Architecture (Phase 9K)

> The target design that removes every single-node SPOF, plus what is **live-verified**
> today on the single-host lab. Referenced by the Phase 9 plan §4 and the 9J security plan.

---

## 1. Goal & current gap

Today every service is single-instance under `docker compose` — Postgres/Timescale,
Redis, Kafka, MinIO, and FastAPI are all SPOFs. HA means: no single node failure causes
data loss or an outage, and the system survives rolling upgrades. True stateful HA needs
**multiple nodes**, so the production target is an orchestrated cluster (Kubernetes).

---

## 2. Target architecture (production)

```
                         ┌─────────────── Ingress (HA) ───────────────┐
   Operators / Mobile ─▶ │  TLS termination · WAF · rate-limit (9J)    │
   Devices/Gateways ──▶  └───────────────┬─────────────────────────────┘
                                         ▼
                         ┌──────────── API tier (stateless) ───────────┐
                         │  FastAPI Deployment, replicas≥3 + HPA         │   ✅ pattern live
                         │  liveness /healthz · readiness /readyz        │
                         └───────┬───────────────┬───────────┬──────────┘
                                 ▼               ▼           ▼
        ┌──────────────┐  ┌──────────────┐ ┌──────────┐ ┌──────────────┐
        │ TimescaleDB  │  │   Redis      │ │  Kafka   │ │   MinIO      │
        │ primary+2 SR │  │ primary+repl │ │ 3 brokers│ │ distributed  │
        │ Patroni/CNPG │  │ + Sentinel   │ │ Strimzi  │ │ (EC 4+)      │
        │ auto-failover│  │ auto-failover│ │ RF=3     │ │ erasure code │
        └──────────────┘  └──────────────┘ └──────────┘ └──────────────┘
   MQTT: clustered broker (EMQX/HiveMQ) or active/standby Mosquitto + shared session store
   Spread across ≥3 nodes / availability zones; anti-affinity per stateful set.
```

### 2.1 Stateless tier — FastAPI (✅ pattern verified live)
- Horizontally scalable (all state externalised). k8s `Deployment` `replicas: 3` + `HPA`
  on CPU/RPS. Rolling updates with `maxUnavailable: 0`.
- Health: **`/healthz`** (liveness — process up, no deps) and **`/readyz`** (readiness —
  DB+Redis reachable; a replica that loses its DB is pulled from the Service endpoints).
- Fronted by a Service + Ingress (the lab demonstrates this with Caddy round-robin).

### 2.2 PostgreSQL / TimescaleDB
- **CloudNativePG** or **Patroni** operator: 1 primary + 2 synchronous/async standbys,
  automatic failover + leader election, continuous WAL archiving to object storage,
  **point-in-time recovery**. Connection routing via the operator's `-rw`/`-ro` Services
  (writes → primary, reads → replicas). Timescale extension on every node.

### 2.3 Redis
- Primary + ≥1 replica with **Redis Sentinel** (3 sentinels for quorum) for automatic
  promotion, or **Redis Cluster** for sharded scale. Clients use the Sentinel-aware URL.
- (Lab: a read-only replica with streaming replication is live — §4.)

### 2.4 Kafka
- **Strimzi** operator: 3 brokers, **replication factor 3**, `min.insync.replicas=2`,
  rack awareness across AZs. KRaft or 3 ZooKeeper nodes. Survives one broker loss with no
  command-bus interruption. (Today: 1 broker, RF=1 — the main remaining Kafka gap.)

### 2.5 MinIO / object storage
- Distributed MinIO (≥4 drives, erasure coding) or a managed object store (S3/GCS). Used
  for WAL archive, backups, and analytics artifacts.

### 2.6 MQTT broker
- A clustered broker (EMQX/HiveMQ/VerneMQ) or active/standby Mosquitto with a shared
  session/persistence store, behind a TCP load balancer. Per-device mTLS (9J-S4) issued by
  the cluster PKI. Devices reconnect to any node; the SDK now re-subscribes on reconnect.

### 2.7 Cross-cutting
- **Anti-affinity** so replicas of a stateful set never co-locate; spread across ≥3 nodes/AZ.
- **PodDisruptionBudgets** so voluntary disruptions never drop quorum.
- **Backups + DR**: WAL/PITR for Postgres, periodic Redis/MinIO snapshots, restore drills.
- **Observability**: Prometheus + Grafana + Alertmanager already present; add Loki/OTel.

---

## 3. Migration path (staged, lab stays up)

| Stage | Action |
|-------|--------|
| K0 | App is orchestration-ready: env-config (9J-S0), `/healthz` + `/readyz` (done) |
| K1 | **Stateless API HA**: ≥2 replicas behind a LB/Service with health checks (✅ live) |
| K2 | Redis primary+replica (+ Sentinel) (✅ replica live; Sentinel = next) |
| K3 | Postgres/Timescale operator (CNPG/Patroni) + standby + WAL archive + PITR |
| K4 | Kafka 3-broker (Strimzi), RF=3, min.insync=2 |
| K5 | MinIO distributed; MQTT cluster + mTLS (with 9J-S4) |
| K6 | Full k8s cutover via Helm; Ingress + TLS (9J-S6); HPA; PDBs; multi-AZ |

---

## 4. What is live-verified on the single host today

| Capability | Live status | Evidence |
|-----------|-------------|----------|
| API horizontal scaling + LB | ✅ | Caddy gateway round-robins `diep-fastapi` + `diep-fastapi-2` |
| API automatic failover | ✅ | killed a replica → all requests served by the survivor (0 errors); rejoined on recovery |
| Liveness/readiness probes | ✅ | `/healthz`, `/readyz` (DB+Redis checked) |
| Redis streaming replication | ✅ | `master_link_status:up`; key written to primary read from replica; replica read-only |
| Postgres/Kafka/MinIO/MQTT HA | ⏳ manifests | needs a multi-node cluster — see `k8s/` |

**Single-host honesty:** the lab LB and the single datastores are still SPOFs on one host;
the *patterns* are proven and the `k8s/` manifests deliver true HA on a real ≥3-node cluster.

---

## 5. Artifacts

- `docker-compose-ha.yml` — live API replica + Caddy LB + Redis replica (this lab).
- `caddy/Caddyfile` — the LB/health-check config (and the 9J-S6 TLS-proxy seam).
- `k8s/` — production Kubernetes manifests (API Deployment/Service/HPA/Ingress/PDB) and the
  operator Custom Resources (CloudNativePG, Strimzi, Redis) for the stateful tiers.
