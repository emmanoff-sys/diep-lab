# DIEP Phase 17 — Production HA Architecture

**Date:** 2026-06-15
**Role:** Senior Platform Architect
**Input:** [`DIEP_FINAL_RELEASE_READINESS_REPORT.md`](DIEP_FINAL_RELEASE_READINESS_REPORT.md)
(95/100, Pilot GO / Production NO-GO), [`DIEP_HA_ARCHITECTURE.md`](DIEP_HA_ARCHITECTURE.md)
(Phase 9K target design and `k8s/` manifests), `DIEP_BACKUP_DR_*` reports (Kafka
checkpoint-corruption incidents, RPO ~24h gap).
**Scope:** Architecture and planning only — **no code or configuration changes** in this
report. Assumes eventual full migration to Kubernetes (Phase 9K `k8s/` manifests as the
landing zone).

---

## 1. Current state summary

DIEP today runs as a single `docker compose` project on one host. Every stateful
component is a single container with a single local volume — i.e. a single point of
failure (SPOF) at the process, disk, and host level simultaneously.

| Component | Image | Persistence | Replication | Known issues |
|---|---|---|---|---|
| TimescaleDB | `timescale/timescaledb:latest-pg16` | `timescale-data` volume | None | Nightly `pg_dump` only → RPO ≈ 24h |
| Kafka | `apache/kafka:latest` (KRaft, combined mode) | `kafka-data` volume | RF=1, `min.insync.replicas=1` | **Checkpoint corruption recurred twice during DR drills**, required manual recovery each time |
| Redis | `redis:7-alpine` | `redis-data` volume (AOF, `appendonly yes`) | None (lab proves primary+replica pattern in `docker-compose-ha.yml`, not in production) | Cache/session/rate-limit state lost on crash |
| MQTT (Mosquitto) | `eclipse-mosquitto` | config + passwd/ACL on disk | None | All device/service mTLS sessions terminate on one broker |
| MinIO | `minio/minio` | `minio-data` volume, single drive | None, no erasure coding | Backup artifact store is itself a SPOF |

This document assesses each of the five stateful components and defines the Phase 17
target HA architecture, building directly on the Phase 9K design and `k8s/` manifests
already drafted (`postgres-cnpg.yaml`, `redis.yaml`, `kafka-strimzi.yaml`).

---

## 2. TimescaleDB / PostgreSQL

### 2.1 Current architecture
- Single `diep-timescaledb` container, PG16 + TimescaleDB extension.
- One volume (`timescale-data`), one filesystem, one host.
- Backups: nightly `pg_dump` to local disk (per backup/DR validation) — full logical
  dump, no WAL archiving, no PITR. RPO ≈ 24h, RTO for a dump-restore ≈ minutes
  (validated at 2.8s for container restart, but that assumes the volume survives).
- Consumers: `fastapi`, `ingestor`, `dispatcher`, `postgres-exporter` — all connect
  directly to `diep-timescaledb:5432`.

### 2.2 Target HA architecture
CloudNativePG (CNPG) operator-managed cluster (`k8s/postgres-cnpg.yaml` is the starting
point):

```
                ┌───────────────────────────────────────────┐
                │              diep-pg (CNPG Cluster)         │
                │                                              │
   writes ────▶ │  diep-pg-rw  ──▶  ● primary (instance-1)     │
   reads  ────▶ │  diep-pg-ro  ──▶  ○ standby (instance-2)     │
                │                ──▶  ○ standby (instance-3)   │
                │                                              │
                │  continuous WAL archiving ──▶ MinIO/S3       │
                │  (barman-cloud, gzip, 30d retention)         │
                └───────────────────────────────────────────┘
        Anti-affinity: 1 instance per node, spread across ≥3 nodes/AZ
```

- 1 primary + 2 standbys, synchronous replication to at least one standby
  (`synchronous_commit = on`, `synchronous_standby_names` via CNPG).
- Continuous WAL archiving to object storage (MinIO distributed cluster, §6) gives
  **point-in-time recovery (PITR)** to any second within the retention window, not just
  the last nightly dump.
- Operator-managed automatic failover (CNPG embeds a Patroni-equivalent DCS using the
  Kubernetes API as the consensus store — no separate etcd/ZK needed).
- `diep-pg-rw` / `diep-pg-ro` Services give the app tier write/read endpoints without
  app-level failover logic.

### 2.3 Failure scenarios
| Scenario | Impact today (single instance) | Impact with HA target |
|---|---|---|
| Container/process crash | Outage until `restart: unless-stopped` recovers (seconds–tens of seconds); no data loss if volume intact | CNPG promotes a standby in ~10-30s; crashed instance rejoins as standby after `pg_rewind` |
| Disk corruption | Outage + possible data loss back to last `pg_dump` (≤24h) | Standby promoted (no data loss for committed sync transactions); old primary rebuilt via `pg_basebackup` from the new primary |
| Host failure | Total outage until host/volume recovered; RPO ≤24h | Surviving 2 instances continue (1 primary + 1 standby); cluster self-heals when node returns |
| Full cluster loss (all 3 nodes/AZ) | N/A (already 1 node) | Restore via `barman-cloud-restore` from MinIO WAL archive → PITR to last archived WAL segment (RPO seconds–minutes, not 24h) |
| Split-brain (two primaries) | N/A | Prevented — CNPG uses the K8s API as single source of truth for leader election; old primary is fenced |

### 2.4 Recovery scenarios
- **Routine failover** (planned maintenance / node drain): CNPG promotes a standby,
  RTO ≈ 10-30s, RPO = 0 (sync replica caught up).
- **Unplanned primary loss**: same automatic promotion; RPO = 0 for synchronously
  committed transactions, ≤ a few hundred ms for async-committed ones.
- **Catastrophic loss (PITR restore)**: `kubectl cnpg restore` from the barman object
  store, target time = any timestamp within the 30-day retention. RTO is dominated by
  base-backup restore time (minutes, proportional to DB size) + WAL replay to target.

### 2.5 Hardware requirements
- 3 nodes (1 primary-capable + 2 standby-capable), spread across ≥3 failure domains
  (hosts or AZs).
- Per node: 4 vCPU, 16 GB RAM, 100 GB fast-SSD (`storageClass: fast-ssd`) — sized for
  the current TimescaleDB footprint (65 MB live data today) plus headroom for
  hypertable growth and WAL.
- Object storage target for WAL archive: the Phase 17 distributed MinIO cluster (§6) or
  an external S3-compatible bucket if MinIO HA is not yet available (see prioritization).

### 2.6 Network requirements
- Low-latency (<5ms) links between the 3 Postgres nodes for synchronous replication —
  ideally same-rack/AZ; cross-AZ sync replication adds write latency.
- Outbound path from each Postgres node to the MinIO/S3 endpoint for continuous WAL
  shipping (`barman-cloud-wal-archive`), bandwidth proportional to write volume.
- Internal ports: 5432 (Postgres), CNPG operator webhook/metrics ports (8000, 9187).
- `diep-pg-rw`/`diep-pg-ro` ClusterIP Services consumed by `fastapi`, `ingestor`,
  `dispatcher` — no app-visible port change from today's `5432`.

### 2.7 Estimated implementation effort
| Item | Effort |
|---|---|
| K1 — PITR only (WAL archiving from current single instance to MinIO/S3, no extra nodes) | **Small** (2-3 days) |
| K2 — Full CNPG 3-instance HA cluster on k8s | **Large** (2-3 weeks, depends on k8s cutover readiness) |

---

## 3. Kafka

### 3.1 Current architecture
- Single broker, KRaft combined mode (`KAFKA_PROCESS_ROLES: broker,controller`,
  `KAFKA_NODE_ID: 1`), `KAFKA_CONTROLLER_QUORUM_VOTERS: 1@localhost:9093`.
- `default.replication.factor` effectively 1 (only one broker exists);
  `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1`,
  `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1`.
- Listeners: `PLAINTEXT://9092` (internal/kafka-ui), `SASL://9094` (app clients,
  SASL_PLAINTEXT, hardcoded credentials in `docker-compose.yml` — flagged separately as
  a Phase 16 security audit item).
- Single `kafka-data` volume holds both broker log segments and KRaft metadata log.
- **Incident history**: the backup/DR drills recorded **checkpoint-file corruption
  recurring twice**, each requiring manual container/volume recovery — the single
  highest-severity operational finding carried into this roadmap.

### 3.2 Target HA architecture
Strimzi operator-managed cluster (`k8s/kafka-strimzi.yaml` is the starting point):

```
        ┌───────────────────────── diep-kafka (Strimzi) ─────────────────────────┐
        │   broker-0 (AZ-a)      broker-1 (AZ-b)      broker-2 (AZ-c)             │
        │   ┌──────────┐         ┌──────────┐         ┌──────────┐               │
        │   │ topic P0 │ ◀─RF3─▶ │ topic P0 │ ◀─RF3─▶ │ topic P0 │  (replicas)    │
        │   └──────────┘         └──────────┘         └──────────┘               │
        │   min.insync.replicas=2 — tolerates 1 broker loss with zero msg loss    │
        │   3-node KRaft controller quorum (or 3 ZK nodes)                        │
        │   rack-aware partition placement (topology.kubernetes.io/zone)          │
        └──────────────────────────────────────────────────────────────────────┘
```

- 3 brokers, `default.replication.factor=3`, `min.insync.replicas=2`,
  `offsets.topic.replication.factor=3`, `transaction.state.log.replication.factor=3`.
- `diep-commands` (and other) topics created with `replicas: 3`.
- SASL_SSL (carrying forward the existing Phase 9J-S5 SASL work, upgraded from
  SASL_PLAINTEXT to TLS) via Strimzi-managed certs.
- Rack awareness (`rack.topologyKey`) so the 3 replicas of any partition land on 3
  different nodes/AZs — directly addresses the single-disk corruption failure mode.

### 3.3 Failure scenarios
| Scenario | Impact today (1 broker, RF=1) | Impact with HA target (3 brokers, RF=3) |
|---|---|---|
| Broker process crash | DERMS command bus down until the single broker restarts | Cluster continues on 2 brokers (≥ min.insync=2); Strimzi restarts the pod, it rejoins and catches up |
| Disk corruption / checkpoint corruption (the recurring incident) | **Total topic data loss** (RF=1); manual recovery required (observed twice) | One replica lost, two intact — no data loss, no manual intervention; Strimzi reprovisions the broker on a fresh PVC and Kafka re-replicates automatically |
| Host/AZ failure | Total command-bus outage | Cluster continues on remaining 2 brokers; rack awareness ensures the lost AZ never held all 3 replicas of a partition |
| Controller quorum node loss | N/A (1 controller) | Tolerates loss of 1 of 3 controllers, quorum maintained |
| Full cluster loss | N/A | Restore from MirrorMaker2 DR replica (if configured) or re-seed from upstream producers (telemetry is re-derivable from device state; DERMS commands are not — see roadmap note on command-log backup) |

### 3.4 Recovery scenarios
- **Single broker loss**: automatic, RTO = time for Strimzi to reschedule the pod +
  re-replicate (typically 1-5 minutes depending on data volume), RPO = 0 (the other 2
  replicas already had the data, `min.insync.replicas=2` guarantees acks=all writes
  were durable on ≥2 brokers before ack).
- **Checkpoint corruption** (the incident this roadmap directly targets): with RF=3,
  a single corrupted broker's log/checkpoint is simply discarded and rebuilt from the
  surviving replicas — no manual recovery runbook needed, vs. the current
  total-loss-and-manual-rebuild outcome.
- **Controller quorum loss (1 of 3)**: automatic re-election, no operator action.

### 3.5 Hardware requirements
- 3 broker nodes, spread across ≥3 failure domains.
- Per broker: 4 vCPU, 16 GB RAM (current single broker uses ~420 MB RSS at light load;
  sized up for headroom + page-cache benefit), 200 GB fast-SSD per broker
  (`storageClass: fast-ssd`) — 3x current single 20GB-class volume to hold RF=3.
- 3-node KRaft controller quorum can be co-located on the broker nodes (combined mode)
  for this scale, or split to 3 small dedicated controller pods if broker I/O isolation
  is desired.

### 3.6 Network requirements
- Inter-broker replication traffic (9093 KRaft controller, internal replication
  listener) needs low-latency links between the 3 broker nodes — same constraints as
  Postgres sync replication.
- App-facing SASL_SSL listener (9094 today, TLS-upgraded in target) reachable from
  `fastapi`, `dispatcher`.
- `kafka-exporter`/`kafka-ui` need read access to the bootstrap servers.
- Rack-awareness requires nodes labeled with `topology.kubernetes.io/zone`.

### 3.7 Estimated implementation effort
**Large** (2-3 weeks). This is the highest-priority stateful migration given the
incident history — see prioritization in §7. Includes: Strimzi operator install,
3-broker `Kafka` CR, topic migration/recreation with RF=3, SASL_SSL cert issuance,
client (`fastapi`, `dispatcher`) bootstrap-server and security-protocol config update,
and a DR drill repeat to confirm the corruption scenario no longer requires manual
recovery.

---

## 4. Redis

### 4.1 Current architecture
- Single `diep-redis` container, `redis:7-alpine`, AOF persistence
  (`appendonly yes`), `requirepass` from `${REDIS_PASSWORD}`.
- Single `redis-data` volume.
- Used for: API rate-limiting state, session/cache data (per Phase 9J/15A security
  reports), checked by `/readyz`.
- The lab's `docker-compose-ha.yml` already proves a primary+replica streaming
  replication pattern live (Phase 9K §4) — this is **not** deployed to production.

### 4.2 Target HA architecture
Redis Sentinel topology (`k8s/redis.yaml`, Bitnami chart, already drafted):

```
        ┌────────────┐      async repl      ┌────────────┐
        │  primary    │ ───────────────────▶ │  replica-1  │
        └─────┬──────┘                       └────────────┘
              │            async repl         ┌────────────┐
              └──────────────────────────────▶│  replica-2  │
                                               └────────────┘
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │ sentinel-1 │  │ sentinel-2 │  │ sentinel-3 │   quorum = 2
        └───────────┘  └───────────┘  └───────────┘
        Clients connect via Sentinel-aware URL; auto-discover current primary.
```

- 1 primary + 2 replicas + 3 sentinels, `quorum: 2`.
- `auth.enabled: true` (existing `REDIS_PASSWORD` carried forward via
  `existingSecret`).
- `podAntiAffinityPreset: hard` so primary/replicas never co-locate.

### 4.3 Failure scenarios
| Scenario | Impact today (1 instance) | Impact with HA target |
|---|---|---|
| Process crash | API `/readyz` fails `redis: false`; rate-limit/session state lost (AOF replay recovers data up to last fsync, but service is down meanwhile) | Sentinels detect within `down-after-milliseconds` (~5s default), promote a replica; clients reconnect to new primary automatically |
| Disk failure | Data loss back to last AOF fsync (≤1s with `appendfsync everysec`) + outage | Promoted replica has async-replicated data (sub-second lag under normal load); failed node's disk loss does not affect the promoted primary |
| Host failure | Total outage | 2 of 3 nodes survive; quorum=2 sentinels still agree, failover proceeds |
| Network partition (sentinel split-brain) | N/A | `quorum: 2` of 3 sentinels prevents a minority partition from forcing an unsafe failover |

### 4.4 Recovery scenarios
- **Primary failure**: Sentinel-driven failover, RTO ≈ 10-15s (detection + promotion +
  client reconfiguration), RPO = replication lag at failure time (typically <1s).
- **Replica failure**: no client-visible impact; Sentinel/Redis re-attaches a new
  replica and it resyncs (full or partial resync).
- **All-node loss**: restore from AOF/RDB snapshot backup (recommend adding scheduled
  RDB snapshot export to MinIO alongside the existing backup automation).

### 4.5 Hardware requirements
- 3 Redis data nodes (1 primary-capable + 2 replicas) + 3 sentinel processes — the
  sentinels are lightweight and can be co-located with other small workloads or run as
  sidecars on the same 3 nodes.
- Per Redis node: 2 vCPU, 4 GB RAM, 8 GB persistent volume (`fast-ssd`) — current usage
  is ~5 MB, sized for headroom and AOF growth.

### 4.6 Network requirements
- Low-latency link primary→replicas for streaming replication (async, so less strict
  than Postgres/Kafka sync paths, but still benefits from same-AZ placement).
- Sentinel gossip/quorum traffic between the 3 sentinel processes and to the data
  nodes (port 26379).
- Clients (`fastapi`) switch from a static `diep-redis:6379` URL to a
  Sentinel-aware connection string — no new external ports, internal-only.

### 4.7 Estimated implementation effort
**Medium** (1 week). The lab has already validated the primary+replica pattern live
(Phase 9K); adding Sentinel and porting to the `k8s/redis.yaml` Helm values is
incremental, not novel.

---

## 5. MQTT (Mosquitto)

### 5.1 Current architecture
- Single `diep-mqtt` container (`eclipse-mosquitto`), mTLS-only on 8883
  (Phase 9J-S4), per-device/service client certs issued by `bootstrap-pki.sh`.
- Legacy password-auth users (`diep-device`, `diep-nodered`) via
  `mosquitto/config/passwd` + ACL.
- All telemetry producers (`ingestor`, simulators, edge drivers) and the
  `dispatcher`/`ev-charger` command consumers connect to this single broker. No
  clustering, no shared session/persistence store.

### 5.2 Target HA architecture
Clustered MQTT broker (EMQX recommended — native clustering via Mnesia, built-in
Prometheus exporter, mTLS support, drop-in replacement for the 8883 mTLS listener):

```
                 ┌──────────────── L4 LB (8883) ────────────────┐
                 │        HAProxy / MetalLB / cloud NLB          │
                 └───────┬───────────────┬───────────────┬──────┘
                          ▼               ▼               ▼
                    ┌──────────┐    ┌──────────┐    ┌──────────┐
                    │ emqx-0   │◀──▶│ emqx-1   │◀──▶│ emqx-2   │   cluster mesh
                    │ (AZ-a)   │    │ (AZ-b)   │    │ (AZ-c)   │   (Mnesia gossip)
                    └──────────┘    └──────────┘    └──────────┘
        Same CA-issued client certs (bootstrap-pki.sh) valid against any node.
        Devices reconnect to any cluster member via the LB on node loss.
```

- 3-node EMQX cluster behind an L4 TCP load balancer on 8883.
- Same per-device mTLS CA/cert model carries forward unchanged (cluster nodes share
  the CA trust chain).
- Persistent sessions (QoS1/2) replicated across the cluster so a reconnecting device
  does not lose queued messages if it lands on a different node.

### 5.3 Failure scenarios
| Scenario | Impact today (1 broker) | Impact with HA target |
|---|---|---|
| Broker process crash | All device/service MQTT connections drop; telemetry and DERMS command delivery halt until restart | LB routes new connections to the 2 surviving nodes; affected devices reconnect (client-side backoff, typically 1-30s) |
| Host/AZ failure | Total MQTT outage | Cluster continues on 2 nodes; rejoining node resyncs cluster state via Mnesia |
| Network partition (cluster split-brain) | N/A | EMQX autoheal reconciles partitioned nodes on reconnect; minority partition rejects new sessions until healed |

### 5.4 Recovery scenarios
- **Single node loss**: LB health check removes the node within its check interval
  (seconds); devices already connected to that node reconnect via LB to a surviving
  node — RTO bounded by client reconnect/backoff settings (typically ≤30s for
  `paho-mqtt` default backoff).
- **Persistent session continuity**: QoS1 in-flight messages for a reconnecting device
  are redelivered from the cluster's replicated session state, not lost.
- **Full cluster loss**: re-deploy from the EMQX cluster manifest + re-issue/re-mount
  the existing CA and per-device certs (certs are not cluster-state, they are
  CA-issued artifacts already managed by `bootstrap-pki.sh`).

### 5.5 Hardware requirements
- 3 EMQX nodes, spread across ≥3 failure domains.
- Per node: 2 vCPU, 4 GB RAM, 10 GB volume (mostly for retained messages and Mnesia
  session state — current Mosquitto footprint is ~5 MB, sized for headroom).

### 5.6 Network requirements
- L4 load balancer (HAProxy, MetalLB, or cloud NLB) terminating 8883 (TCP
  passthrough — mTLS terminates at the EMQX nodes, not the LB, to preserve per-device
  client cert identity).
- EMQX cluster mesh ports between the 3 nodes (default `4370` epmd, `5370`
  inter-node — same-AZ/low-latency preferred).
- All existing device-side config (`MQTT_BROKER`, `MQTT_PORT: 8883`, cert paths)
  unchanged from the device's point of view — only the broker behind the LB changes.

### 5.7 Estimated implementation effort
**Large** (2-3 weeks). This is a broker *substitution* (Mosquitto → EMQX), not a
config change — requires validating ACL-equivalent rules, the legacy
password-auth users, retained-message behavior, and re-running the full device fleet
(BAT001/EV001/INV001/MG001/METER001 + ingestor/dispatcher) against the new cluster
before cutover. Lowest urgency of the five given current device counts (see §7).

---

## 6. MinIO

### 6.1 Current architecture
- Single `diep-minio` container, single `minio-data` volume, no erasure coding —
  `command: server /data --console-address ":9001"` (single-drive standalone mode).
- Current usage: backup artifact storage (per backup/DR validation), with headroom for
  future analytics-artifact storage.
- **Dependency note**: K1 (Postgres PITR, §2) and the Kafka/Postgres backup pipelines
  all want a durable object-storage target — today that target is itself a SPOF.

### 6.2 Target HA architecture
Distributed MinIO, single pool, erasure coding:

```
        ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ minio-0  │  │ minio-1  │  │ minio-2  │  │ minio-3  │
        │ (drive)  │  │ (drive)  │  │ (drive)  │  │ (drive)  │
        └──────────┘  └──────────┘  └──────────┘  └──────────┘
              \____________ erasure set (EC:2) ____________/
        Tolerates loss of up to 2 of 4 drives/nodes with zero data loss.
        Optional: bucket replication to a secondary site/cloud for off-site DR.
```

- Minimum 4 nodes/drives in one erasure set, `EC:2` (2 parity shards) — tolerates 2
  simultaneous drive/node failures.
- Buckets used: PITR WAL archive (`diep-backups/pg`, consumed by K1/K2), pg_dump/config
  backup artifacts (existing automation), future analytics exports.
- Optional MinIO bucket replication to an off-site/secondary MinIO or cloud S3 for
  cross-site DR (addresses "full cluster loss" scenarios in §2/§3).

### 6.3 Failure scenarios
| Scenario | Impact today (1 node, no EC) | Impact with HA target (4 nodes, EC:2) |
|---|---|---|
| Drive/node failure | Total loss of all stored objects (backups, WAL archive) | Up to 2 of 4 nodes can fail with zero data loss; MinIO continues serving in degraded mode |
| Host failure | Backup store unavailable; downstream PITR restores impossible | Cluster continues on 3 nodes; healing scanner repairs the erasure set when the node returns |
| >2 simultaneous node failures | N/A (already total loss at 1 node) | Data loss for affected erasure sets — mitigated by off-site bucket replication |

### 6.4 Recovery scenarios
- **Single drive/node failure**: automatic — no client-visible impact, healing runs in
  background once the node rejoins.
- **Two simultaneous failures**: still served from the remaining 2 nodes (read/write
  continue in degraded mode); restore the failed nodes and the healing scanner
  rebuilds parity.
- **Site loss (if bucket replication configured)**: fail over PITR/backup consumers to
  the secondary site's MinIO endpoint; RPO = replication lag of the bucket replication
  job (minutes, configurable).

### 6.5 Hardware requirements
- 4 nodes minimum (single erasure set), spread across ≥4 failure domains if possible
  (or 4 drives across fewer nodes as an interim step — full HA wants node-level
  isolation too).
- Per node: 2 vCPU, 4 GB RAM, storage sized to backup retention policy (current usage
  is 80 MB; size for 30-day Postgres WAL retention (K1) + existing pg_dump/config
  backup cadence — recommend starting at 100 GB/node and monitoring growth).

### 6.6 Network requirements
- Inter-node traffic for erasure-coded read/write (all 4 nodes participate in every
  object's erasure set) — same-AZ/low-latency preferred; this is the most
  bandwidth-sensitive of the five components under write load.
- S3 API port 9000 reachable from Postgres nodes (WAL archiving, K1/K2) and from the
  existing backup automation/cron.
- Console port 9001 for operational access (internal only).

### 6.7 Estimated implementation effort
**Medium-Large** (1.5-2 weeks). Functionally a clean lift from single-node to
distributed MinIO (same API, same client config — only the endpoint and node count
change), but gated on having ≥4 nodes available, and is a **dependency for K1's
durable WAL-archive target** (see prioritization, §7).

---

## 7. Prioritization (K1–K6)

| Priority | Item | Rationale |
|---|---|---|
| **1** | **K1 — PostgreSQL PITR** | Smallest effort (Small, 2-3 days), runs against the **existing single Postgres instance** — no multi-node prerequisite. Directly closes the 95/100 report's largest named gap (RPO ≈ 24h → seconds/minutes). Can ship to the pilot immediately. |
| **2** | **K4 — Redis Sentinel** | Medium effort, and the underlying primary+replica pattern is **already live-verified** in the lab (Phase 9K). Removes a SPOF that affects every API request path (`/readyz` dependency). Low risk, fast payoff. |
| **3** | **K6 — MinIO HA** | Medium-Large effort. Prioritized ahead of K2/K3 because it is a **dependency**: K1's WAL archive and the existing backup automation both need a durable object-storage target, and K2 (Postgres HA) will lean on the same target for PITR at cluster scale. Do this before scaling Postgres/Kafka backups depend on it further. |
| **4** | **K3 — Kafka HA** | Large effort, but addresses the **highest-severity recurring incident** in the platform (checkpoint corruption, twice manually recovered). Once K6 provides a durable object store, Kafka HA (RF=3) is the next biggest reliability win — eliminates the manual-recovery runbook entirely. |
| **5** | **K2 — PostgreSQL HA** | Large effort, full CNPG 3-instance cluster — builds directly on K1 (PITR/WAL-archiving config is reused) and K6 (object store already proven). Sequencing after K3 because Kafka's incident history is more urgent than upgrading an already-stable (if SPOF) Postgres instance. |
| **6** | **K5 — MQTT HA** | Large effort, and a full broker substitution (Mosquitto → EMQX). Lowest urgency: current device counts (6 devices/services) tolerate brief reconnects, and this requires the most extensive fleet-wide validation. Schedule last, ideally alongside the full K6 (full k8s cutover). |

**Sequencing summary:** K1 → K4 → K6 → K3 → K2 → K5. Items 1-2 (K1, K4) are
single-host-compatible quick wins deployable before any Kubernetes work begins. Items
3-6 (K6, K3, K2, K5) assume the Kubernetes landing zone (`k8s/` manifests) is
available, and are sequenced by incident severity and dependency order.

---

## 8. Cross-cutting Kubernetes considerations

- All target architectures above map onto the existing `k8s/` manifests
  (`postgres-cnpg.yaml`, `redis.yaml`, `kafka-strimzi.yaml`) plus two new manifests to
  be added in Phase 17 planning: a MinIO distributed `Tenant` CR (MinIO Operator) and
  an EMQX cluster CR (EMQX Operator) or Helm release.
- **Anti-affinity and PodDisruptionBudgets** apply uniformly: every stateful
  component's replicas must never co-locate, and voluntary disruptions (node drains,
  upgrades) must never drop below quorum/`min.insync.replicas`.
- **Observability**: Prometheus/Grafana/Alertmanager (Phase 15B) already scrape
  `postgres-exporter` and `kafka-exporter`; Strimzi, CNPG, Bitnami Redis, and EMQX all
  ship their own Prometheus metrics — no new monitoring stack needed, only new scrape
  targets.
- **Secrets**: all five components currently read credentials from `.env` /
  `env_file`. The k8s target uses `Secret` objects (`diep-pg-credentials`,
  `diep-redis-credentials`, etc.) — this is a natural point to also close the Phase 16
  "rotate remaining secrets" gap from the final readiness report, but that rotation is
  tracked separately and is **not** part of this HA roadmap's scope.
