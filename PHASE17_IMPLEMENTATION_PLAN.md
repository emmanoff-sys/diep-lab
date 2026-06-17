# DIEP Phase 17 — HA Implementation Plan

**Date:** 2026-06-15
**Role:** Senior Platform Architect
**Input:** [`DIEP_PHASE17_HA_ARCHITECTURE.md`](DIEP_PHASE17_HA_ARCHITECTURE.md) (per-component
assessment and K1-K6 prioritization), [`DIEP_FINAL_RELEASE_READINESS_REPORT.md`](DIEP_FINAL_RELEASE_READINESS_REPORT.md)
(95/100 baseline).
**Scope:** Migration sequencing, rollback strategy, and expected readiness impact.
**No code changes** — this is a planning document; each stage below produces its own
implementation/validation reports when executed.

---

## 1. Goal

Take DIEP from a single-host deployment (95/100, Pilot GO / Production NO-GO) to a
Kubernetes-based, no-SPOF production architecture, in six prioritized stages
(K1→K4→K6→K3→K2→K5, per the architecture doc §7), each independently shippable and
independently revertible.

---

## 2. Current vs. target topology

### 2.1 Current (single host, all SPOFs)

```
┌──────────────────────────── single host (docker compose) ────────────────────────────┐
│                                                                                          │
│  fastapi ── ingestor ── dispatcher ── portal ── nodered ── ev-charger                   │
│     │            │            │                                                         │
│     ▼            ▼            ▼                                                         │
│  ┌─────────┐  ┌──────┐  ┌─────────┐  ┌──────┐  ┌───────┐                                │
│  │timescale│  │ kafka│  │  redis  │  │ mqtt │  │ minio │   ◀── each: 1 instance,        │
│  │   db    │  │ (1br)│  │ (1node) │  │(1node)│  │(1node)│       1 volume, 1 host        │
│  └─────────┘  └──────┘  └─────────┘  └──────┘  └───────┘                                │
│       │                                                                                  │
│       └──▶ nightly pg_dump (local disk)   ◀── RPO ≈ 24h                                 │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Target (post Phase 17, Kubernetes, ≥3 nodes/AZs)

```
┌────────────────────────────────── Kubernetes cluster (≥3 nodes/AZ) ───────────────────────────────────┐
│                                                                                                           │
│   FastAPI Deployment (replicas:3) ── Ingestor/Dispatcher/Portal/NodeRED/EV-charger (stateless)          │
│         │              │                    │                  │                                        │
│         ▼              ▼                    ▼                  ▼                                        │
│  ┌──────────────┐ ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐                            │
│  │ diep-pg (CNPG)│ │ diep-kafka    │  │ Redis Sentinel │  │ EMQX cluster (3) │                            │
│  │ 1 primary +   │ │ (Strimzi)     │  │ 1 primary +    │  │ behind L4 LB     │                            │
│  │ 2 standbys    │ │ 3 brokers     │  │ 2 replicas +   │  │ on 8883          │                            │
│  │ sync repl     │ │ RF=3, isr=2   │  │ 3 sentinels    │  │                  │                            │
│  └──────┬────────┘ └──────┬────────┘  └────────────────┘  └──────────────────┘                          │
│         │ continuous WAL archive       │                                                                 │
│         ▼                              ▼                                                                 │
│  ┌─────────────────────────────────────────────────────┐                                                │
│  │ Distributed MinIO (4 nodes, EC:2)                     │  ◀── PITR archive + backups, durable          │
│  │   optional bucket replication ──▶ off-site/secondary  │                                                │
│  └─────────────────────────────────────────────────────┘                                                │
│                                                                                                           │
│  Anti-affinity + PodDisruptionBudgets across all stateful sets; Prometheus/Grafana/Alertmanager (15B)    │
│  scrape postgres-exporter / kafka-exporter / Redis & EMQX exporters / CNPG & Strimzi operator metrics.   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Migration strategy (staged, K1 → K4 → K6 → K3 → K2 → K5)

Each stage follows the same pattern used successfully in Phase 16
(remediate → revalidate side-by-side → confirm production unaffected → cut over):
build the new component **alongside** the existing one, validate it independently, then
cut traffic over, and only decommission the old component after a soak period.

### Stage 1 — K1: PostgreSQL PITR (single-host compatible)
**Goal:** Continuous WAL archiving from the existing `diep-timescaledb` instance to an
object-storage target, closing the ≈24h RPO gap without any new nodes.

1. Stand up an interim object-storage target for the WAL archive — either the
   existing single-node `diep-minio` (acceptable as an interim target since K1 is
   explicitly sequenced *before* K6 in the architecture doc, but K6 should follow
   promptly to remove this as a new SPOF) or an external S3-compatible bucket if
   available sooner.
2. Configure `archive_mode`/`archive_command` (or `pgbackrest`/`barman` agent) on
   `diep-timescaledb` to continuously ship WAL segments to the chosen bucket, in
   addition to (not replacing) the existing nightly `pg_dump`.
3. Validate: take a base backup, generate transactions, perform a PITR restore to a
   point in time *after* the base backup but *before* "now" into a scratch instance;
   confirm the restored data matches expectations and the recovered timestamp is
   correct.
4. Document the new RPO (target: seconds-to-minutes, bounded by WAL-shipping
   frequency) and the PITR restore runbook.

**Dependencies:** none (runs against the current single instance).
**Validation gate:** a successful PITR restore drill into a scratch instance, with no
impact on the running `diep-timescaledb` container.

### Stage 2 — K4: Redis Sentinel (single-host compatible, k8s-ready)
**Goal:** Eliminate the Redis SPOF using the already-live-verified primary+replica
pattern, extended with Sentinel.

1. Add 2 Redis replicas (streaming replication from `diep-redis`, as already proven in
   `docker-compose-ha.yml`) and 3 Sentinel processes, `quorum: 2`.
2. Update the FastAPI Redis client config to use a Sentinel-aware connection (service
   name + sentinel endpoints) instead of the static `diep-redis:6379` URL.
3. Validate: kill the current primary, confirm Sentinel promotes a replica within
   ~10-15s, confirm `/readyz` stays `redis: true` throughout (or recovers within the
   expected window), confirm `REDIS_PASSWORD` auth still enforced post-failover.
4. Port the validated topology into `k8s/redis.yaml` (already drafted) for the
   eventual cluster cutover — this stage can run on the single host first and be
   re-deployed to k8s later without redesign.

**Dependencies:** none.
**Validation gate:** primary-kill failover drill with `/readyz` and rate-limit state
checks passing.

### Stage 3 — K6: MinIO HA (requires ≥4 nodes)
**Goal:** Replace the single-node MinIO with a distributed, erasure-coded cluster —
removing the SPOF underneath K1's WAL archive and the existing backup automation.

1. Provision 4 nodes (or 4 drives across available nodes as an interim step).
2. Deploy distributed MinIO (`EC:2`), migrate existing bucket contents
   (`diep-backups/*`) from the single-node instance via `mc mirror`.
3. Re-point K1's WAL-archive command and the existing pg_dump/config-backup cron at
   the new distributed endpoint (same S3 API, only the endpoint changes).
4. Validate: kill 1, then 2, of the 4 MinIO nodes; confirm reads/writes continue in
   degraded mode and the healing scanner repairs the erasure set on node return.
5. (Optional, can defer) configure bucket replication to an off-site/secondary
   target for cross-site DR.

**Dependencies:** K1 (so there's a meaningful WAL archive to migrate); ≥4 available
nodes (first hard Kubernetes-cluster-sized prerequisite in this plan).
**Validation gate:** 2-of-4 node-loss drill with zero data loss; WAL archiving and
backup cron both confirmed writing successfully to the new endpoint.

### Stage 4 — K3: Kafka HA (Strimzi, 3 brokers)
**Goal:** Eliminate the recurring checkpoint-corruption failure mode by moving from
1 broker/RF=1 to 3 brokers/RF=3/`min.insync.replicas=2`.

1. Deploy Strimzi operator + `k8s/kafka-strimzi.yaml` (3 brokers, 3-node KRaft
   controller quorum, rack-aware).
2. Recreate topics (`diep-commands`, etc.) with `replicas: 3`, `min.insync.replicas:2`.
3. Update `fastapi`/`dispatcher` bootstrap-server and security-protocol config
   (SASL_PLAINTEXT → SASL_SSL with Strimzi-managed certs).
4. Run the DR drill from `DIEP_BACKUP_DR` reports that previously triggered checkpoint
   corruption (or an equivalent fault-injection: kill a broker pod's PVC) — confirm
   the cluster self-heals with **zero manual recovery**, directly closing this
   roadmap's highest-severity finding.
5. Cut producers/consumers over to the new cluster; run side-by-side for a soak
   period before decommissioning the single-broker instance.

**Dependencies:** K6 (durable object store available for any future Kafka backup/DR
tooling), Kubernetes cluster available.
**Validation gate:** broker-pod-kill / disk-loss drill with zero message loss and zero
manual intervention; side-by-side soak period (recommend 1 week) before decommission.

### Stage 5 — K2: PostgreSQL HA (CNPG, 3 instances)
**Goal:** Extend K1's PITR setup into a full 1-primary + 2-standby CNPG cluster with
automatic failover.

1. Deploy CNPG operator + `k8s/postgres-cnpg.yaml` (3 instances, anti-affinity,
   `backup.barmanObjectStore` pointed at the K6 MinIO cluster).
2. Bootstrap the cluster from a base backup of the current `diep-timescaledb`
   (`pg_basebackup` or logical restore from the existing pg_dump), then enable
   streaming replication to the 2 standbys.
3. Re-point `fastapi`/`ingestor`/`dispatcher`/`postgres-exporter` at `diep-pg-rw` /
   `diep-pg-ro` Services.
4. Validate: kill the primary pod, confirm CNPG promotes a standby in ~10-30s with
   RPO=0 for sync-committed transactions; confirm `/readyz` recovers within the
   expected window.
5. Run side-by-side with the existing single instance during the soak period;
   decommission only after a successful PITR restore drill against the *new* cluster's
   WAL archive (re-validating K1's runbook at cluster scale).

**Dependencies:** K1 (WAL-archiving config reused), K6 (object store target).
**Validation gate:** primary-kill failover drill (RTO/RPO measured) + PITR restore
drill against the new cluster's archive.

### Stage 6 — K5: MQTT HA (EMQX cluster, broker substitution)
**Goal:** Replace single-node Mosquitto with a 3-node EMQX cluster behind an L4 LB,
preserving the existing mTLS PKI model.

1. Deploy a 3-node EMQX cluster; configure it to trust the existing
   `bootstrap-pki.sh`-issued CA and validate per-device client certs identically to
   Mosquitto's current ACL model.
2. Recreate ACL-equivalent authorization rules (per-device topic permissions) in
   EMQX's authorization config; migrate the legacy `diep-device`/`diep-nodered`
   password-auth users.
3. Stand up an L4 TCP load balancer (HAProxy/MetalLB) on 8883 in front of the 3 EMQX
   nodes, passthrough TLS (mTLS terminates at EMQX nodes).
4. Validate against the **full device fleet** (BAT001, EV001, INV001, MG001,
   METER001, ingestor, dispatcher, ev-charger): each connects via the LB, publishes/
   subscribes successfully, and DERMS commands round-trip end-to-end (re-running the
   F4 site-scoped DERMS validation from `DEPLOYMENT_REVALIDATION_REPORT.md` against
   the new broker).
5. Kill 1 of 3 EMQX nodes mid-test; confirm devices reconnect via the LB to a
   surviving node and QoS1 messages are not lost.
6. Cut the production fleet over (re-point `MQTT_BROKER` to the LB endpoint); run
   side-by-side soak; decommission Mosquitto.

**Dependencies:** Kubernetes cluster, L4 LB capability. Sequenced last as the most
invasive change (broker substitution) and least urgent (current device count
tolerates brief outages).
**Validation gate:** full device-fleet connectivity + DERMS round-trip on the new
broker, plus a node-kill drill with zero message loss for QoS1 traffic.

---

## 4. Rollback strategy

Every stage is designed to run **alongside** the existing component until validated,
so rollback is "don't cut over" / "re-point back," not "undo a destructive change":

| Stage | Rollback mechanism |
|---|---|
| **K1 — PITR** | Purely additive (new `archive_command`, new backup target). Rollback = disable `archive_mode`/stop the WAL-shipping agent; the existing nightly `pg_dump` continues unchanged throughout. No data or service impact either way. |
| **K4 — Redis Sentinel** | Replicas/Sentinels are additive nodes; FastAPI's connection string is the only changed config. Rollback = revert the connection string to the static `diep-redis:6379` URL; remove replicas/sentinels at leisure. The original primary is never touched. |
| **K6 — MinIO HA** | Bucket contents are mirrored (not moved) to the new cluster. Rollback = re-point WAL-archive/backup cron back at the single-node `diep-minio` endpoint (kept running, unmodified, until decommission). |
| **K3 — Kafka HA** | New cluster runs side-by-side with the original single broker during the soak period; clients are re-pointed via config (`bootstrap.servers`), not in-place upgrade. Rollback = re-point `fastapi`/`dispatcher` back to the original broker's `9094` listener, which remains untouched and running. Decommission only after the soak period. |
| **K2 — PostgreSQL HA** | New CNPG cluster is bootstrapped from a backup/replica of the original instance, which remains running and untouched. Rollback = re-point `diep-pg-rw`/app connection strings back to `diep-timescaledb:5432`. Decommission only after a successful PITR drill on the new cluster. |
| **K5 — MQTT HA** | EMQX cluster validated against the full fleet while Mosquitto continues serving production traffic. Rollback = re-point `MQTT_BROKER` env var back to `diep-mqtt` (unchanged, still running with its original certs/ACLs). Decommission only after the fleet-wide soak period. |

**General principle carried from Phase 16:** no stage modifies or restarts the
production component it is replacing until the replacement has been independently
validated and a soak period has passed — exactly the side-by-side validation pattern
used for the Phase 16 deployment revalidation (`val2-diep-*` containers alongside
`diep-*`).

---

## 5. Expected readiness improvement

Current baseline (from `DIEP_FINAL_RELEASE_READINESS_REPORT.md`):

| Category | Current | 
|---|---|
| Core DERMS functionality | 20/20 |
| Security | 16/20 |
| Monitoring & observability | 17/20 |
| Operations (backup/DR) | 17/20 |
| Deployment hygiene | 15/20 |
| Documentation | 10/10 |
| **Total** | **95/100** |

Phase 17 primarily affects **Operations (backup/DR)** and **Deployment hygiene**
(SPOF elimination); Security/Monitoring/DERMS/Documentation improvements are tracked
under separate initiatives (secret rotation, TLS, etc.) and are out of scope here.

| Stage | Operations impact | Deployment hygiene impact | Running total |
|---|---|---|---|
| Baseline | 17/20 | 15/20 | **95/100** |
| K1 — PostgreSQL PITR | 17→19 (RPO ≈24h → seconds/minutes, the largest named gap) | — | **97/100** |
| K4 — Redis Sentinel | — | 15→16 (1 of 5 SPOFs removed) | **98/100** |
| K6 — MinIO HA | 19→20 (backup/WAL-archive target now durable) | 16→17 (2 of 5 SPOFs removed) | **100/100*** |
| K3 — Kafka HA | (already at 20; closes the recurring-incident finding qualitatively) | 17→18 (3 of 5 SPOFs removed) | **100/100*** |
| K2 — PostgreSQL HA | (already at 20) | 18→19 (4 of 5 SPOFs removed) | **100/100*** |
| K5 — MQTT HA | (already at 20) | 19→20 (5 of 5 SPOFs removed — no remaining single-instance stateful components) | **100/100*** |

\* Capped at the 20/20 ceiling per category — totals beyond 100 are not awarded; later
stages convert *qualitative* reliability wins (e.g., Kafka's recurring incident
becoming a non-event) into headroom/robustness rather than additional points, since
Operations and Deployment hygiene reach their category ceilings at K6.

**Net effect:** completing K1+K4+K6 (Stages 1-3, all deployable on the current
single-host topology or with a modest 4-node MinIO expansion) is sufficient to reach
**100/100** on this scoring model and directly addresses every open item the final
readiness report flagged for Operations/Deployment hygiene. K3, K2, and K5 (Stages
4-6) are then justified primarily by **production-grade reliability** (eliminating the
Kafka incident class, removing the last two SPOFs) ahead of the
`RELEASE_CERTIFICATION_REPORT.md` Production NO-GO being revisited — i.e., they are the
work that converts "100/100 on a single host" into "Production: GO" by removing the
single-host topology itself.

---

## 6. Summary timeline

| Stage | Item | Effort | Prerequisite infra |
|---|---|---|---|
| 1 | K1 — PostgreSQL PITR | Small (2-3 days) | None |
| 2 | K4 — Redis Sentinel | Medium (1 week) | None |
| 3 | K6 — MinIO HA | Medium-Large (1.5-2 weeks) | ≥4 nodes |
| 4 | K3 — Kafka HA | Large (2-3 weeks) | Kubernetes cluster (Strimzi) |
| 5 | K2 — PostgreSQL HA | Large (2-3 weeks) | Kubernetes cluster (CNPG), K1, K6 |
| 6 | K5 — MQTT HA | Large (2-3 weeks) | Kubernetes cluster, L4 LB |

Stages 1-2 are deployable immediately on the current single host. Stage 3 requires the
first hardware expansion (≥4 nodes). Stages 4-6 assume the Kubernetes landing zone
(`k8s/` manifests, Phase 9K) is stood up and each runs its own side-by-side
validation + soak period before decommissioning the predecessor component, per §4.
