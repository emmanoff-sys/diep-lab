# DIEP Phase 9K — High Availability

> **Status:** Stateless API-tier HA + Redis replication **live-verified**; full stateful HA
> delivered as production Kubernetes manifests. Date: 2026-06-05. The running 5-vertical
> stack stayed intact throughout (all PRODUCTION_READY, telemetry uninterrupted).
> Architecture: `DIEP_HA_ARCHITECTURE.md`. Manifests: `k8s/`.

---

## 1. Summary & honest scope

9K's true target is a multi-node orchestrated cluster — you cannot make Postgres, Kafka,
MinIO, or the MQTT broker genuinely HA on a **single host**. So 9K is delivered in two
honest parts:

1. **Live-verified on the lab host** — the patterns that *don't* need multiple nodes:
   - **Stateless API HA**: a load balancer round-robins 2 FastAPI replicas, with active
     health checks and **automatic failover** (verified by killing a replica).
   - **Redis streaming replication** (primary → read-only replica).
   - **Orchestration health probes** (`/healthz`, `/readyz`) the LB/k8s use.
2. **Production manifests (`k8s/`)** — the stateful HA a single host can't run: CloudNativePG
   (Postgres/Timescale primary+2 replicas, failover, PITR), Strimzi Kafka (3 brokers, RF=3),
   Redis Sentinel, distributed MinIO, plus the API `Deployment + HPA + Ingress + PDB`.

Nothing in the running stack was disturbed — the HA pieces are **additive** (`docker-compose-ha.yml`).

---

## 2. What was built

### 2.1 Health/readiness probes (`fastapi/app.py`)
- **`/healthz`** — liveness; returns `{status, instance}` (the serving replica's hostname),
  no dependency checks so a transient DB blip never flaps the LB.
- **`/readyz`** — readiness; checks DB + Redis, returns 200/503. k8s pulls a not-ready pod
  from Service endpoints without killing it.

### 2.2 Load-balanced API replicas (`docker-compose-ha.yml`, `caddy/Caddyfile`)
- A 2nd stateless replica `diep-fastapi-2` (the API holds no local state — all in
  Postgres/Redis/Kafka).
- A **Caddy gateway** (`diep-api`, host :8090) round-robins both replicas with active
  `/healthz` checks; a failing replica is evicted from the pool automatically.

### 2.3 Redis replication
- `diep-redis-replica` streams from the primary (`replicaof`), read-only.

### 2.4 Production Kubernetes manifests (`k8s/`)
- `api.yaml` — `Deployment replicas:3` + rolling update (`maxUnavailable:0`) + topology
  spread + liveness/readiness + **HPA (3→10)** + **PodDisruptionBudget** + TLS **Ingress**.
- `postgres-cnpg.yaml` — CloudNativePG 3-instance Timescale cluster, anti-affinity, WAL
  archiving + daily base backup + **PITR**.
- `kafka-strimzi.yaml` — 3 brokers, RF=3, `min.insync.replicas=2`, rack-aware, SASL_SSL.
- `redis.yaml` — Redis + Sentinel (auto-failover).
- `secrets.example.yaml` — secret template (sealed-secrets/Vault in prod).

---

## 3. Validation (see DIEP_PHASE9K_VALIDATION snippet below)

| Test | Result |
|------|--------|
| LB round-robins 2 replicas | alternating `diep-fastapi-2` ↔ `ea87b5b2bf60` ✓ |
| Real authenticated call via gateway | `GET /assets` → 200 ✓ |
| **API failover** — kill a replica | 6/6 requests served 200 by the survivor; dead replica evicted ✓ |
| **API recovery** — restart replica | rejoined round-robin ✓ |
| `/readyz` checks DB+Redis | `{ready:true, checks:{database:true, redis:true}}` ✓ |
| Redis replication | `master_link_status:up`; key on primary read from replica; replica read-only ✓ |
| Stack intact | 5/5 verticals PRODUCTION_READY; all 5 publishing in last 20 s ✓ |
| k8s manifests | parse clean (api / cnpg / strimzi / secrets) ✓ |

---

## 4. Single-host limitations (stated plainly)

- The lab **LB is itself an SPOF** on one host; in k8s the Service+Ingress are HA.
- The datastores (Postgres, Kafka, MinIO, MQTT) are **still single instances** on the lab —
  true HA for them needs the multi-node cluster the `k8s/` manifests target (stages K3–K5 in
  the HA architecture doc).
- Redis has a live replica but **no Sentinel** yet (manual promotion) — Sentinel is in
  `k8s/redis.yaml`.

---

## 5. Remaining HA stages (per HA architecture §3)

| Stage | Work | Needs |
|-------|------|-------|
| K3 | Postgres/Timescale operator (CNPG) + standbys + WAL/PITR | k8s cluster |
| K4 | Kafka 3-broker (Strimzi), RF=3 | k8s cluster |
| K5 | MinIO distributed; MQTT cluster + per-device mTLS (with 9J-S4) | k8s cluster |
| K6 | Full Helm cutover; Ingress + TLS (9J-S6); HPA; PDBs; multi-AZ | k8s cluster + CI/CD (10A/10B) |

9K is tightly coupled to **Phase 10A (orchestration/IaC)** and **10B (CI/CD)** — the actual
cluster migration happens there. The app is already orchestration-native (env config from
9J-S0, `/healthz`+`/readyz` from 9K), so no further app changes are required for the cutover.

---

## 6. Result & next

Stateless API HA and Redis replication are **live and verified**; the full stateful-HA
design is captured as runnable production manifests. The headline single-node-API SPOF is
addressed in pattern and ready to deploy at `replicas: 3` on a cluster.

**Next per the roadmap:** **Phase 10A (IaC/orchestration)** to stand up the actual k8s
cluster and apply `k8s/`, then **10B (CI/CD)** to build/sign/deploy the API image — these
turn the verified patterns + manifests into a running HA system. In parallel, **9J-S4
(mTLS)** remains the security prerequisite for field actuation.
