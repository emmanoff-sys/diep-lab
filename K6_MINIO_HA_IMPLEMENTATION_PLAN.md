# K6 — MinIO High Availability
## Implementation Plan

**Phase:** 17, Stage 3 (K6 — MinIO HA)
**Status:** Design + side-by-side validation (no production changes yet)
**Author:** Senior Platform Architect (DIEP)
**Date:** 2026-06-16
**Prerequisites:** K1 (PITR validated, WAL archive pipeline defined), K4 (Redis Sentinel validated)

---

## 1. Objective

Replace the single-node MinIO instance (`diep-minio`) with a 4-node distributed MinIO
cluster using Reed-Solomon erasure coding (EC:2), making the object-storage layer that
backs K1's WAL archive and the existing nightly backup pipeline resilient to simultaneous
failure of up to 2 of 4 nodes with zero data loss.

This closes the last single-host SPOF that remains after K1 and K4: K1's PITR WAL
archive is only as durable as the MinIO target it writes to — today that target is a
single container and single volume.

---

## 2. Current State Assessment

| Item | Current value | Source |
|---|---|---|
| Container | `diep-minio` (`minio/minio:latest`) | `docker-compose-minio.yml` |
| Mode | Standalone (`server /data`), single drive, no erasure coding | `docker-compose-minio.yml` |
| Persistence | `minio-data` volume (single Docker named volume, single host) | `docker-compose-minio.yml` |
| Ports | 9000 (S3 API, internal), 9002→9001 (console, external) | `docker-compose-minio.yml` |
| Network | `diep-lab_diep-net` | `docker-compose-minio.yml` |
| Buckets in use | `diep-backups` (nightly pg_dump), `diep-config-backups` (config/cron backup) | `scripts/backup-db.sh`, `scripts/backup-config.sh` |
| K1 WAL buckets | `diep-wal-archive`, `diep-pg-basebackups` (validated, not yet live in production) | `K1_PITR_VALIDATION_REPORT.md` |
| WAL endpoint | `http://diep-minio:9000` | `pitr-validation/scripts/ship-wal.sh` |
| Failure tolerance | Zero — any I/O error, OOM, or volume corruption loses all stored objects | Single container/volume |

---

## 3. HA Solution Evaluation

| Approach | Erasure coding | Failure tolerance | Client change | Effort |
|---|---|---|---|---|
| **MinIO distributed (4 nodes, EC:2)** | ✅ Native Reed-Solomon | Up to 2 of 4 nodes with zero data loss | None — same S3 API, same port | Medium |
| MinIO multi-site replication | ✅ Per-site erasure | Cross-site DR only (not intra-site HA) | None | Medium-Large |
| External S3 (cloud provider) | Handled by provider | Provider SLA | Endpoint change only | Small (but external dependency) |
| GlusterFS or Ceph behind MinIO | Decoupled from MinIO | High, complex | None | Large |

**Selection: MinIO distributed (4 nodes, EC:2).**

Rationale:
- Same `minio/minio` image already in use — zero new image dependencies.
- Identical S3 API: `archive_command`, `ship-wal.sh`, `backup-db.sh`, and all other
  consumers change only the endpoint hostname, not the protocol, SDK, or bucket layout.
- EC:2 with 4 nodes gives 50% storage efficiency and tolerates 2 simultaneous node
  failures — precisely the architecture document's target (§6.2 of
  `DIEP_PHASE17_HA_ARCHITECTURE.md`).
- MinIO's self-healing scanner automatically restores lost erasure shards when a failed
  node rejoins — no operator intervention required.

---

## 4. Target Design

### 4.1 Topology

```
        ┌─────────────────────────── diep-minio-ha cluster ─────────────────────────────┐
        │                                                                                  │
        │   minio-ha-0   minio-ha-1   minio-ha-2   minio-ha-3                            │
        │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                         │
        │   │ /data   │  │ /data   │  │ /data   │  │ /data   │     ← separate drives    │
        │   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘                         │
        │        └────────────┴────────────┴────────────┘                                │
        │               single erasure set, EC:2                                          │
        │          (2 data shards + 2 parity shards per object)                          │
        │                                                                                  │
        │   Write quorum: 3 of 4 nodes   Read quorum: 2 of 4 nodes                      │
        └──────────────────────────────────────────────────────────────────────────────┘
                              │ S3 API (:9000)
                              ▼
              Consumers: ship-wal.sh, backup-db.sh, fastapi exporters
              (endpoint: http://minio-ha-0:9000 or NLB in production)
```

### 4.2 Erasure Code Parameters

| Parameter | Value | Notes |
|---|---|---|
| Drives per erasure set | 4 | One container/volume per node |
| Data shards (k) | 2 | Minimum blocks needed to reconstruct an object |
| Parity shards (m) | 2 | EC:2 — MinIO default for N=4 |
| Write quorum | 3 | Need N/2 + 1 = 3 nodes online to accept new writes |
| Read quorum | 2 | Need N/2 = 2 nodes online to serve reads of existing objects |
| Max simultaneous failures (zero data loss) | 2 | 2 remaining nodes can reconstruct any object |
| Storage efficiency | 50% | 2 of 4 shards carry data |

### 4.3 Startup Configuration

All 4 MinIO nodes start with identical commands specifying all 4 peers. MinIO uses this
URL list to form the distributed pool and establish the erasure set:

```
minio server \
  http://minio-ha-0:9000/data \
  http://minio-ha-1:9000/data \
  http://minio-ha-2:9000/data \
  http://minio-ha-3:9000/data \
  --console-address ":9001"
```

All nodes share the same `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` (a MinIO
distributed-mode requirement — all nodes must have identical credentials).

### 4.4 Client Configuration Changes (production rollout, deferred)

| Consumer | Current endpoint | Target endpoint | Other changes |
|---|---|---|---|
| `pitr-validation/scripts/ship-wal.sh` | `http://diep-minio:9000` | `http://diep-minio-ha:9000` | None |
| `scripts/backup-db.sh` | `http://diep-minio:9000` | `http://diep-minio-ha:9000` | None |
| `scripts/backup-config.sh` | `http://diep-minio:9000` | `http://diep-minio-ha:9000` | None |
| K2 WAL archive (Patroni `archive_command`) | `http://diep-minio:9000` | `http://diep-minio-ha:9000` | None |
| MINIO_ROOT_USER / MINIO_ROOT_PASSWORD | From `.env` | Rotated to new production credentials | All 4 nodes must use same value |

A production load balancer (`diep-minio-ha:9000`) would sit in front of the 4 nodes;
for validation, `minio-ha-0:9000` is used as the direct entry point (all nodes serve
the same data regardless of which node receives the S3 request).

---

## 5. Implementation Steps

| Step | Action |
|---|---|
| 1 | Assess current state (Section 2) — complete |
| 2 | Select HA solution (Section 3) — complete |
| 3 | Design target architecture (Section 4) — complete |
| 4 | Write `docker-compose-minio-ha-validation.yml` (4-node isolated stack, throwaway credentials) |
| 5 | Write `minio-ha-validation/scripts/ship-wal-ha.sh` (K1 WAL shipper pointing at distributed cluster) |
| 6 | Bring up validation stack: `docker compose -f docker-compose-minio-ha-validation.yml -p diep-minio-ha-val up -d` |
| 7 | Verify cluster formation: `mc admin info` shows 4 online nodes, 1 erasure set |
| 8 | Run Phase 1 — basic CRUD validation (create bucket, put/get/list/delete objects) |
| 9 | Run Phase 2 — single-node failure drill (stop minio-ha-3; verify reads + writes continue with 3 nodes) |
| 10 | Run Phase 3 — two-node failure drill (stop minio-ha-2; verify reads continue, writes fail; 2 nodes = read quorum boundary) |
| 11 | Run Phase 4 — self-heal (restart failed nodes; verify healing scanner restores erasure parity) |
| 12 | Run Phase 5 — WAL archive simulation (upload WAL-named objects, kill 1 node, verify objects still accessible) |
| 13 | Run Phase 6 — PITR compatibility (`ship-wal-ha.sh` against distributed cluster, verify bucket layout identical to K1) |
| 14 | Record all results in `K6_MINIO_HA_VALIDATION_REPORT.md` |
| 15 | Tear down validation stack and volumes; confirm production `diep-minio` / `minio-data` untouched |

---

## 6. Validation Plan

| # | Check | Pass criteria |
|---|---|---|
| 1 | Cluster formation | `mc admin info` shows 4 nodes online, 1 erasure set, status OK |
| 2 | Erasure set configuration | EC:2 confirmed (2 data + 2 parity shards) |
| 3 | Bucket creation | `mc mb` succeeds; bucket visible from all 4 nodes |
| 4 | Object write (baseline) | `mc put` succeeds, object listed in bucket |
| 5 | Object read (baseline) | `mc get` returns identical bytes to uploaded object |
| 6 | **Single-node failure — writes** | `docker stop minio-ha-3` → `mc put` succeeds (3 nodes ≥ write quorum 3) |
| 7 | **Single-node failure — reads** | Existing objects readable with 3 nodes remaining |
| 8 | **Two-node failure — reads** | `docker stop minio-ha-2` also → existing objects still readable (2 nodes = read quorum) |
| 9 | **Two-node failure — writes** | New `mc put` fails (2 nodes < write quorum 3) — expected and documented |
| 10 | **Self-heal** | Restart minio-ha-2 and minio-ha-3 → `mc admin heal` shows 0 objects needing repair after heal completes |
| 11 | **WAL archive simulation** | Upload 10 WAL-named objects (`000000010000...`); kill 1 node; verify all 10 readable |
| 12 | **PITR compatibility** | `ship-wal-ha.sh` creates `diep-wal-archive-ha-test` and `diep-pg-basebackups-ha-test` buckets, uploads WAL-like objects; mc mirror log shows no errors |
| 13 | **Data durability** | After full cluster restore, all objects uploaded before/during failure drills are present and identical |
| 14 | **Production isolation** | `diep-minio` container and `minio-data` volume confirmed untouched throughout |

---

## 7. Rollback Procedure

The validation stack is entirely isolated from production (`diep-minio`, `minio-data`).
No production rollback is required for the validation work itself.

For the deferred production rollout (Section 8), rollback is re-pointing clients:

| Step | Rollback action |
|---|---|
| WAL shipper (`ship-wal.sh`) | Revert `MINIO_ENDPOINT` to `http://diep-minio:9000`; single-node MinIO continues running throughout |
| Backup scripts | Same — revert endpoint variable; existing `diep-backups` / `diep-config-backups` on `diep-minio` are untouched |
| Distributed cluster | `docker compose -f docker-compose-minio-ha.yml down` (production compose, once created) — volumes retained so data is preserved |
| Bucket migration | Bucket contents were mirrored (not moved) via `mc mirror` from `diep-minio` to the HA cluster; original buckets on `diep-minio` are unmodified and serve as instant fallback |

**General principle**: `diep-minio` stays running and unmodified until after a soak
period with the HA cluster receiving all production traffic and a successful PITR restore
drill against the new cluster's WAL archive.

---

## 8. Production Rollout (deferred — not part of this stage)

Only after `K6_MINIO_HA_VALIDATION_REPORT.md` shows PASS for all checks:

1. Write `docker-compose-minio-ha.yml` (production compose, reusing the validated node
   count and command configuration, with production credentials from `.env`).
2. Bring up the 4-node distributed cluster on `diep-lab_diep-net`, allocating persistent
   named volumes `minio-ha-0-data` … `minio-ha-3-data` (separate from `minio-data`).
3. Mirror existing bucket contents from `diep-minio` to the HA cluster:
   ```
   mc mirror m-old/diep-backups m-ha/diep-backups
   mc mirror m-old/diep-config-backups m-ha/diep-config-backups
   ```
4. Create K1 WAL buckets on the HA cluster (`diep-wal-archive`, `diep-pg-basebackups`).
5. Update `MINIO_ENDPOINT` in the WAL shipper sidecar and backup cron scripts to point
   at the HA cluster (or the NLB endpoint in front of it).
6. Run a full PITR restore drill against WAL segments archived to the HA cluster
   (re-validating `K1_PITR_IMPLEMENTATION_PLAN.md` §5 runbook against the new target).
7. Monitor for 48h soak period; confirm all backup/WAL-archive jobs write successfully.
8. Decommission `diep-minio` and remove the `minio-data` volume only after soak passes.
9. Update `.env.example` and `docker-compose-minio.yml` to reflect the HA configuration.

---

## 9. Durability and Availability Summary

| Scenario | Current (single node) | After K6 (4 nodes, EC:2) |
|---|---|---|
| Node/process crash | All stored objects inaccessible; WAL archive unavailable; PITR recovery impossible | Cluster continues on 3 surviving nodes; reads and writes unaffected (3 ≥ write quorum) |
| 1-of-4 node failure | Total loss | Reads ✅ Writes ✅ (write quorum met) |
| 2-of-4 node failure | Total loss | Reads ✅ Writes ❌ (below write quorum; data preserved, recoverable once node count ≥ 3) |
| Volume corruption (1 node) | Data loss proportional to corrupted extents; backups potentially unrecoverable | Erasure parity on surviving 3 nodes reconstructs all objects; self-healing restores parity on repaired node |
| Full cluster loss | N/A (already total loss at 1 node) | Mitigated by MinIO bucket replication to secondary site (optional, Phase 17 §6.2 — not required for this stage) |
| WAL archive availability during 1-node failure | Unavailable | WAL segments remain readable + new segments continue uploading ✅ |
| WAL archive availability during 2-node failure | Unavailable | Existing WAL segments readable for PITR recovery ✅; new segment uploads fail ❌ until ≥3 nodes restored |

**RPO impact**: The 2-node-failure write-unavailability window does not cause WAL data
loss — segments already archived are safe. New segments queue in the local `wal-archive`
staging volume and ship once the cluster recovers to ≥3 nodes. The local staging
volume (`archive_command`'s target) prevents WAL loss during the failure window.
