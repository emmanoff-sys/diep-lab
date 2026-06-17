# K3 — Kafka HA Implementation Plan

**Phase:** 17, Stage 4 (K3)
**Date:** 2026-06-15
**Status:** Design + side-by-side validation (this stage). Production rollout
(Section 6) is deferred to a scheduled cutover after a soak period, per
`PHASE17_IMPLEMENTATION_PLAN.md` §4.

---

## 1. Objective

Eliminate `diep-kafka` as a single point of failure and as the source of the
recurring checkpoint-corruption incident class (`backups/kafka-redis-*/
*-checkpoint.bak`) by moving from **1 broker / RF=1** to a **3-broker KRaft
cluster** with `default.replication.factor=3` and `min.insync.replicas=2`,
while preserving the existing SASL_PLAINTEXT/PLAIN authentication and the
`diep.commands` topic schema used by the DERMS command flow.

---

## 2. Current State Assessment

| Item | Current value | Source |
|---|---|---|
| Image | `apache/kafka:latest` (4.2.0) | `docker-compose.yml` |
| Container | `diep-kafka`, single node | `docker-compose.yml` |
| Mode | KRaft, combined `broker,controller`, `node.id=1` | `KAFKA_PROCESS_ROLES`, `KAFKA_NODE_ID` |
| Controller quorum | `1@localhost:9093` (single voter) | `KAFKA_CONTROLLER_QUORUM_VOTERS` |
| Listeners | `PLAINTEXT://:9092` (internal/kafka-ui), `CONTROLLER://:9093`, `SASL://:9094` (`SASL_PLAINTEXT`, app clients) | `KAFKA_LISTENERS` |
| Auth | SASL/PLAIN, `username="diep"`, JAAS-embedded password, single user | `KAFKA_LISTENER_NAME_SASL_PLAIN_SASL_JAAS_CONFIG` |
| Topics | `diep.commands` — 1 partition, **RF=1**, `min.insync.replicas=1`; `__consumer_offsets` — 50 partitions, RF=1 | `kafka-topics.sh --describe` |
| `default.replication.factor` | 1 | `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1`, `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1`, `KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1` |
| `auto.create.topics.enable` | `true` | env |
| Storage | single named volume `kafka-data` | `docker-compose.yml` |
| Producer | `fastapi/app.py` — `KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, acks="all", ...)`, `KAFKA_BOOTSTRAP=diep-kafka:9094`, `SASL_PLAINTEXT`/`PLAIN`, user `diep` | `fastapi/app.py:55-62,218-223` |
| Consumer | `dispatcher/command_dispatcher.py` — `KafkaConsumer` on `diep.commands`, same bootstrap/SASL config, retry-loop connect | `dispatcher/command_dispatcher.py:35-49,155-183` |
| k8s draft | `k8s/kafka-strimzi.yaml` — Strimzi `Kafka` (3 replicas, `replicas: 3`, `min.insync.replicas: 2`, SCRAM-SHA-512/TLS) + `KafkaTopic diep-commands` (6 partitions, RF=3, `min.insync.replicas: 2`) — drafted, not deployed | `k8s/kafka-strimzi.yaml` |
| Known incident | Recurring checkpoint-corruption (`recovery-point-offset-checkpoint.bak`, `log-start-offset-checkpoint.bak` under `backups/kafka-redis-*`) — single-broker RF=1 means any unclean shutdown/disk issue on `diep-kafka` can corrupt the only copy of the log/checkpoint state, with no replica to recover from | `backups/kafka-redis-20260615045613/` |
| RTO today | Manual: operator restarts `diep-kafka`; if checkpoint files are corrupted, broker fails to start until checkpoints are repaired/removed (the recurring incident) — **no automatic recovery, possible message loss** | n/a |

**Key finding:** Kafka here is the DERMS command bus — `fastapi` produces to
`diep.commands` (`acks="all"`), `dispatcher` consumes and routes to devices
over MQTT. With RF=1, a single broker disk/process failure both halts the
command flow and can corrupt the only log copy (the incident class this
stage targets). Both clients already use `kafka-python` with a configurable
`bootstrap_servers`/SASL block, so the migration is a **config-only** change
on the client side — no code restructuring needed.

---

## 3. Target Design

### 3.1 Topology

```
                    ┌────────────────────────────────────────────┐
                    │           diep-net (bridge)                 │
                    │                                              │
  fastapi (producer)│   ┌──────────────┐                          │
  dispatcher(consumer)─▶│ kafka-val-1  │◀─┐  KRaft combined        │
                    │   │ node.id=1    │  │  broker+controller     │
                    │   │ 9092/9093/9094│  │  quorum (3 voters)     │
                    │   └──────────────┘  │                        │
                    │   ┌──────────────┐  │                        │
                    │   │ kafka-val-2  │◀─┼─ controller.quorum.    │
                    │   │ node.id=2    │  │  voters =              │
                    │   └──────────────┘  │  1@kafka-val-1:9093,   │
                    │   ┌──────────────┐  │  2@kafka-val-2:9093,   │
                    │   │ kafka-val-3  │◀─┘  3@kafka-val-3:9093    │
                    │   │ node.id=3    │                            │
                    │   └──────────────┘                           │
                    │   topic diep.commands.val: 6 partitions,      │
                    │   RF=3, min.insync.replicas=2                 │
                    └────────────────────────────────────────────┘

  Client (kafka-python): bootstrap_servers=[kafka-val-1:9094,
  kafka-val-2:9094, kafka-val-3:9094], SASL_PLAINTEXT/PLAIN — any broker
  can be used as the initial bootstrap; the client discovers partition
  leaders for the rest of the brokers via metadata.
```

### 3.2 Configuration Changes

| Setting | Current (`diep-kafka`) | Target (3-broker validation / production) |
|---|---|---|
| Brokers | 1 (`node.id=1`) | 3 (`node.id=1,2,3`), each `process.roles=broker,controller` |
| `controller.quorum.voters` | `1@localhost:9093` | `1@kafka-val-1:9093,2@kafka-val-2:9093,3@kafka-val-3:9093` |
| `default.replication.factor` | 1 | 3 |
| `offsets.topic.replication.factor` | 1 | 3 |
| `transaction.state.log.replication.factor` | 1 | 3 |
| `transaction.state.log.min.isr` | 1 | 2 |
| `min.insync.replicas` (broker default for new topics) | 1 | 2 |
| `auto.create.topics.enable` | `true` | `false` (explicit RF=3 topic creation) |
| `diep.commands` topic | 1 partition, RF=1, `min.insync.replicas=1` | `diep.commands`: 6 partitions, RF=3, `min.insync.replicas=2` (matches `k8s/kafka-strimzi.yaml` `KafkaTopic`) |
| SASL | `SASL_PLAINTEXT`/`PLAIN`, user `diep` | Unchanged mechanism/protocol; same JAAS module, same credential, all 3 brokers share the JAAS config |
| Client `bootstrap_servers` | `diep-kafka:9094` (single host) | `diep-kafka-1:9094,diep-kafka-2:9094,diep-kafka-3:9094` (comma-separated list; `kafka-python` rediscovers leaders/metadata automatically — clients reconnect to any live broker) |
| Client code | `fastapi/app.py`, `dispatcher/command_dispatcher.py` | No code change — both already read `KAFKA_BOOTSTRAP` from env as a comma-separated string |

### 3.3 Rollout Mechanics (production, deferred — Section 6)

1. Add `kafka-2`/`kafka-3` services to `docker-compose.yml` (or deploy
   `k8s/kafka-strimzi.yaml` via Strimzi operator — the longer-term target),
   each with `process.roles=broker,controller`, joining the existing
   `diep-kafka` (`node.id=1`) controller quorum. This requires `diep-kafka`'s
   `controller.quorum.voters` to be updated to list all 3 nodes —
   **the only change to the existing broker**, and is a config/restart, not
   a data-destructive change (KRaft supports adding voters to a quorum).
2. Recreate `diep.commands` with RF=3 / `min.insync.replicas=2` (6 partitions)
   — since the topic is small and the consumer is a single dispatcher
   instance with no persisted offset dependency beyond `__consumer_offsets`
   (also moving to RF=3), this can be done via `kafka-topics.sh
   --alter --partitions 6` plus `kafka-reassign-partitions.sh` for RF, or by
   draining/recreating during a low-traffic window.
3. Update `KAFKA_BOOTSTRAP` for `fastapi` and `dispatcher` to the
   3-broker list; no other code change (`_kafka_security_kwargs()` is
   already generic).
4. Rolling restart: `dispatcher` then `fastapi` (producer `acks="all"` means
   in-flight messages are not lost during the bounce).
5. Run the fault-injection drill that previously produced checkpoint
   corruption (kill `-9` a broker, or remove its volume) — confirm the
   cluster **self-heals with zero manual recovery** (the highest-severity
   finding this stage closes).

---

## 4. Implementation Steps (this stage)

1. ✅ Assess current Kafka deployment (Section 2).
2. ✅ Design 3-broker KRaft + topic config (Section 3).
3. ✅ Produce this plan document.
4. Build `docker-compose-kafka-ha-validation.yml`: 3-node KRaft cluster
   (`kafka-val-1/2/3`), combined broker+controller, SASL_PLAINTEXT/PLAIN
   (throwaway credential), attached to the existing `diep-lab_diep-net`,
   separate named volumes, no host port mapping (clients run as containers on
   the same network).
5. Validate: replica sync of `diep.commands.val` (RF=3), Sentinel-equivalent
   for Kafka = `kafka-topics.sh --describe` showing 3 in-sync replicas;
   producer/consumer via `kafka-python` mirroring the production client
   pattern; leader election and durability across broker restarts.
6. Simulate: broker crash (`docker kill`), network partition (`docker
   network disconnect`/`connect`), controller failure (kill the active
   KRaft quorum leader) — measure leader-election time, producer/consumer
   failover time, and message loss (offset accounting before/after).
7. Tear down the validation stack; confirm `diep-kafka` (production) was
   never stopped, reconfigured, or had its topics/data touched.
8. Produce `K3_KAFKA_HA_VALIDATION_REPORT.md`.
9. (Deferred) Production rollout per Section 3.3 / Section 6.

---

## 5. Validation Plan

Isolated stack `docker-compose-kafka-ha-validation.yml`, project
`diep-kafka-ha-val`, on `diep-lab_diep-net`:

| # | Step | Expected result |
|---|---|---|
| 1 | Bring up `kafka-val-1/2/3` (KRaft, combined roles, shared `CLUSTER_ID`) | All 3 report `running`; `kafka-metadata-quorum.sh describe` shows 3 voters, 1 leader |
| 2 | Create `diep.commands.val` — 6 partitions, RF=3, `min.insync.replicas=2` | `kafka-topics.sh --describe` shows each partition with 3 replicas, ISR=3 |
| 3 | Produce N messages via `kafka-python` (SASL_PLAINTEXT/PLAIN, `acks="all"`) | All N acknowledged; `kafka-console-consumer`/`kafka-python` consumer reads back N messages, in order per partition |
| 4 | **Broker crash**: `docker kill` the partition leader for a sample partition | New leader elected from the remaining ISR within seconds; producer (with `retries`) and consumer resume with zero message loss |
| 5 | **Producer failover**: producer's bootstrap broker is the killed one | `kafka-python` reconnects via the remaining bootstrap servers / refreshed metadata; in-flight `acks="all"` sends either succeed on the new leader or are retried |
| 6 | **Consumer failover**: consumer group rebalances if the killed broker hosted the group coordinator | Group coordinator re-elected on a surviving broker; consumer resumes from last committed offset, no duplicate/missing messages beyond at-least-once semantics |
| 7 | **Restart killed broker** | Rejoins as follower, catches up ISR; `kafka-topics.sh --describe` returns to ISR=3 |
| 8 | **Network partition**: `docker network disconnect` the current leader | Remaining 2 brokers (quorum) detect, elect new leader; partitioned broker rejoins as follower on `connect` |
| 9 | **Controller failure**: kill the active KRaft controller (`kafka-metadata-quorum.sh describe` → leader id) | Remaining 2 controller voters elect a new controller leader; broker metadata operations continue |
| 10 | Cache/data durability check | `kafka-console-consumer --from-beginning` on `diep.commands.val` after all drills returns exactly the produced messages, no gaps/duplicates beyond expected at-least-once retries |
| 11 | Teardown | `docker compose -p diep-kafka-ha-val down -v`; confirm `diep-kafka` (prod) unchanged: `diep.commands` topic, `DBSIZE`/offsets, container never restarted |

---

## 6. Production Rollout (deferred, NOT executed in this stage)

1. Add `kafka-2`, `kafka-3` services to `docker-compose.yml`, each
   `process.roles=broker,controller`, `node.id=2`/`3`, sharing
   `diep-kafka`'s `CLUSTER_ID` and SASL JAAS config (`${KAFKA_SASL_PASSWORD}`
   from `.env`).
2. Update `diep-kafka`'s `KAFKA_CONTROLLER_QUORUM_VOTERS` to the 3-node list
   (controller quorum reconfiguration — additive, does not require
   reformatting `diep-kafka`'s existing storage).
3. Recreate/alter `diep.commands` to 6 partitions / RF=3 /
   `min.insync.replicas=2`; set `default.replication.factor=3`,
   `offsets.topic.replication.factor=3`,
   `transaction.state.log.replication.factor=3`,
   `transaction.state.log.min.isr=2`, `auto.create.topics.enable=false`
   cluster-wide (applies to new brokers; `diep-kafka`'s existing
   `__consumer_offsets` (RF=1) can be left as-is or reassigned to RF=3 via
   `kafka-reassign-partitions.sh`).
4. Update `KAFKA_BOOTSTRAP` env for `fastapi`/`dispatcher` to
   `diep-kafka:9094,diep-kafka-2:9094,diep-kafka-3:9094`; rolling restart
   `dispatcher` then `fastapi`.
5. Run the fault-injection drill (kill a broker / corrupt its volume) that
   previously produced checkpoint corruption; confirm self-healing.
6. Port the validated topic/replication config into `k8s/kafka-strimzi.yaml`
   for the eventual Strimzi cutover (already drafted with RF=3,
   `min.insync.replicas: 2`).

---

## 7. Rollback Procedure

| Stage | Rollback action |
|---|---|
| Validation stack (this stage) | `docker compose -f docker-compose-kafka-ha-validation.yml -p diep-kafka-ha-val down -v` — removes all 3 validation brokers and volumes. Zero production impact since `diep-kafka` was never referenced. |
| Production rollout (Section 6, future) | Re-point `KAFKA_BOOTSTRAP` for `fastapi`/`dispatcher` back to `diep-kafka:9094` only (single value) — `diep-kafka` (`node.id=1`) remains running and untouched throughout, so this is an env-var change + rolling restart, no data migration to reverse. Newly added `kafka-2`/`kafka-3` services and their volumes can then be removed; if `diep.commands` was already widened to RF=3/6 partitions, it can remain (RF=3 with 1 surviving broker simply degrades to ISR=1, same as today) or be reverted via `kafka-reassign-partitions.sh`. |

`diep-kafka` is never stopped, reformatted, or have its `CLUSTER_ID`/storage
touched by this stage — the validation cluster has its own `CLUSTER_ID` and
volumes.

---

## 8. RTO / Failover Targets

| | Before (current, single `diep-kafka`, RF=1) | Target (K3, 3-broker, RF=3/min.insync.replicas=2) |
|---|---|---|
| Broker failure detection | None (manual) | Automatic, via KRaft controller heartbeats (`broker.session.timeout.ms`, default 9s) |
| Leader election | N/A (no replicas) | Automatic, target **<10s** |
| Producer impact | Total outage until manual restart; possible checkpoint corruption | `acks="all"` producer retries against new leader, target **<10s** outage, zero message loss (write succeeded on `min.insync.replicas=2` before ack) |
| Consumer impact | Total outage until manual restart | Consumer group rebalance to surviving brokers, target **<15s**, resumes from committed offset |
| Data durability | Single copy — corruption = data loss (the recurring incident) | 3 copies, `min.insync.replicas=2` — tolerates 1 broker loss with zero data loss |
| Controller failure | N/A (single voter = total outage) | 3-voter KRaft quorum tolerates 1 controller loss, target **<10s** new controller leader |
