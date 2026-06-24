# Host / VM Instability — Findings for Hypervisor Team (2026-06-24)

**Prepared from inside the guest, read-only. No changes were made.**
**Purpose:** evidence to drive a hypervisor/VM-host-level fix. The remediation
(vCPU allocation, virtual disk controller/cache mode, host scheduling) is **outside
the guest** and requires VMware host / datastore access this guest does not have.

---

## 1. Summary

The DIEP platform VM (`projectlab`) has suffered **two state-corruption incidents**
across unclean restarts:

1. containerd metadata `boltdb` panic — `page N: multiple references`.
2. (current) redis-sentinel-2/-3 rendered configs `/data/sentinel.conf` came back
   holding **another file's content** (VS Code / Monaco editor JavaScript) at the
   same byte size + original inode mtime; and the container objects for
   `diep-redis`, `diep-redis-replica`, `diep-kafka`, `diep-kafka-exporter` were
   **lost entirely** (data volumes intact).

Both share the signature of **writes acknowledged to the guest but never durably
persisted before an unclean reset** (inode metadata journaled; data block stale).
The guest filesystem itself is **clean** (ext4 `errors_count = 0`, mounted `rw`,
no media/I-O errors). The driver is **host-level CPU/I-O starvation + unclean
restarts**, evidenced below.

## 2. Guest-visible configuration

| Item | Value |
|---|---|
| Hypervisor | **VMware** (full virt); `VMware Virtual Platform/440BX`, BIOS 2020 |
| Host CPU | Intel **i5-4570** (4 cores / 4 threads, Haswell desktop) |
| vCPUs allocated | **4** (4 sockets × 1 core) — i.e. **all 4 host cores, no headroom** |
| Memory | 7.2 GiB; at incident: ~0.8 GiB free, swap in use (~690 MiB) |
| Disk | `sda` 150 GB, VMware Virtual disk, presented **rotational**, `mq-deadline` |
| SCSI controller | **LSI53C1030 / mptspi** (LSI Logic *Parallel* — legacy default) |
| Guest write cache | `/sys/block/sda/queue/write_cache = **write through**` (guest is durable; gap is host-side) |
| Root FS | ext4 on LVM `ubuntu--vg`; **errors_count = 0**, mounted `rw` (no corruption recorded) |

## 3. Boot-storm kernel log (this boot — booted 03:45:12 UTC)

```
2026-06-24T03:48:16Z  workqueue: blk_mq_run_work_fn hogged CPU for >10000us 4 times
2026-06-24T03:50:24Z  watchdog: BUG: soft lockup - CPU#2 stuck for 52s! [alertmanager]
2026-06-24T03:50:24Z  watchdog: BUG: soft lockup - CPU#3 stuck for 52s! [redis-sentinel]
2026-06-24T03:50:24Z  rcu: INFO: rcu_preempt detected stalls on CPUs/tasks
2026-06-24T03:50:24Z  rcu: rcu_preempt kthread starved for 59543 jiffies ... ->cpu=1
2026-06-24T03:50:24Z  rcu:   Unless rcu_preempt kthread gets sufficient CPU time, OOM is now expected behavior
2026-06-24T03:51:34Z  workqueue: blk_mq_run_work_fn hogged CPU for >10000us 35 times
2026-06-24T03:58:51Z  workqueue: blk_mq_run_work_fn hogged CPU for >10000us 131 times
```

Interpretation: vCPUs stuck for 52 s, the RCU grace-period kthread **starved on
cpu=1**, and the **block-I/O workqueue (`blk_mq_run_work_fn`) hogging CPU 131×** —
the guest was CPU- and I-O-starved for ~13 minutes after boot. (ext4 logged no
errors, so this is scheduling/I-O starvation, not media failure.)

## 4. Root-cause hypothesis

The VM is allocated **4 vCPUs on a 4-core host**, leaving no cores for the host/
hypervisor → severe vCPU contention → soft lockups + RCU stalls + block-I/O
workqueue starvation. Combined with **unclean restarts**, in-flight writes cached
at the **VMware host/datastore layer** were lost on reset, so files return with
stale (foreign) block contents. This is consistent across both corruption
incidents and has **recurred**, so it is systemic, not a one-off.

## 5. Recommended host-side actions (require VMware host / datastore access)

1. **Right-size vCPUs** — do not allocate all host cores. Leave headroom (e.g.
   2 vCPUs on this 4-core host), or relocate the VM to a host with more cores /
   lower overcommit.
2. **Switch SCSI controller** LSI Parallel → **VMware Paravirtual (PVSCSI)**.
3. **Guarantee write durability** — confirm the VMDK disk mode is
   *dependent / persistent*, and the datastore is not acknowledging writes from a
   **volatile** host cache (no battery-backed write-back acking the guest).
4. **Add memory headroom** — the storm coincided with swap use / near-OOM.
5. **Eliminate hard resets / power loss** — every corruption correlates with an
   unclean restart; ensure graceful guest shutdowns.
6. After the fix: perform a **clean reboot cycle** and confirm `journalctl -k`
   shows **no** soft lockups / RCU stalls / `blk_mq` hogging.

## 6. Not determinable from inside the guest (needs host access)

- Physical host capacity and **overcommit ratio** (how many VMs share the host).
- VMware **datastore type and host-side disk cache mode** / VMDK disk mode.
- Whether VMware Tools / balloon driver is active.
- An offline **`fsck -f`** of the root FS (belt-and-braces; ext4 reports clean but
  cannot be run live). **Not attempted here** — requires a maintenance window /
  host access.

## 7. DIEP state (held, unchanged)

- Data volumes **intact**: `redis-data` (dump.rdb + AOF), `kafka-data`
  (1.1 GB, `__cluster_metadata` + `__consumer_offsets`), timescale/minio/wal-archive.
- redis/redis-replica/kafka/kafka-exporter **left absent**; sentinel-2/-3 **left
  crash-looping** — evidence preserved, no recovery attempted.
- **MW2 = NO-GO, Production = DENIED, DO-NOT-GO-LIVE** — final for this cycle until
  the host-level fix + clean reboot is confirmed.

---

## Parked-State Snapshot — 2026-06-24 09:41Z

Addendum appended after a **partial recovery attempt** (authorized: redis AOF
torn-tail fix only). Timeline of this document: original host diagnosis (§1–7
above) → recovery attempt → current held state (this section). Recovery was
**halted** when a "beyond torn-tail" corruption surfaced on kafka. Nothing is being
recovered further until the host write-durability fix lands.

### Critical service state (7 critical + 3 sentinels)

| Service | State | Notes |
|---|---|---|
| diep-fastapi | running (restarts=0) | healthy since 04:29Z boot |
| diep-timescaledb | running (restarts=0) | healthy; data intact |
| diep-minio | running (restarts=0) | healthy |
| **diep-redis** (master) | running (restarts=0) | **RECOVERED** — AOF torn tail fixed, loaded clean, role:master, dbsize=1 |
| diep-redis-replica | **exited** (stopped) | torn-tail AOF intact & un-fixed; halted to prevent churn |
| diep-kafka | **exited** (stopped) | KRaft metadata checkpoint corrupted (foreign content); untouched |
| diep-kafka-exporter | **absent** | never started (depends on kafka) |
| diep-redis-sentinel-1 | running (restarts=0) | healthy |
| diep-redis-sentinel-2 | restarting (×319) | crash-loop on corrupt config — confirmed NOT writing to volume |
| diep-redis-sentinel-3 | restarting (×319) | crash-loop on corrupt config — confirmed NOT writing to volume |

### Confirmed data loss
**Total: 1,178 bytes — redis master AOF only** (the torn final write, dropped by the
approved `redis-check-aof --fix`). Nothing else was modified.

### Damaged-but-untouched state (no loss yet; deferred to post-host-fix)
- **redis-replica** AOF `appendonly.aof.3.incr.aof`: 1,178-byte torn tail,
  intact/un-fixed (recover later via `--fix` or full resync from the healthy master).
- **kafka** `__cluster_metadata-0/leader-epoch-checkpoint`: foreign Monaco-JS content
  (block-reuse corruption), untouched. A prior `.corrupt-20260623T124907Z` backup
  shows this same file was corrupted once before — recurring.
- **sentinel-2/-3** `/data/sentinel.conf`: foreign Monaco-JS content, untouched
  (mtime stable at 2026-06-23 20:55:13 across ~319 restarts → not mutating).

### State-mutation safety (verified)
- redis master idle/healthy; redis-replica + kafka **stopped** (not writing);
  kafka-exporter absent.
- sentinel-2/-3 crash-loop is **read-then-die** — the entrypoint only seeds
  `sentinel.conf` when absent; here it exists (corrupt), so it skips seeding and
  `exec`s redis-sentinel, which aborts on the parse error before any write. Conf
  mtime unchanged for ~12.75 h → **no volume mutation**.
- Data volumes (`redis-data`, `redis-replica-data`, `kafka-data`, `timescale-data`,
  `minio-data`, `wal-archive`) all present and preserved.
- (FYI, not investigated further: 2-vCPU load avg ~2.6–3.7 — still elevated,
  consistent with the unresolved I/O substrate issue.)

### Standing root cause — UNRESOLVED
**Host write-durability gap** (VMware guest; LSI-parallel SCSI; datastore/host-side
cache not yet hardened). The vCPU reduction addressed CPU starvation but **not**
durability — corruption **recurred this session** (replica + kafka). Pending on the
host side: cache mode / barriers / clean-shutdown discipline / `fsck` in a
maintenance window.

### Decisions held (unchanged)
**MW2 = NO-GO · Production = DENIED · DO-NOT-GO-LIVE.** 24h stability clock **not**
restarted; MW2 **not** re-assessed.

### Resume plan (on operator confirmation "host stable — proceed with recovery")
redis-replica fix/resync → kafka-data integrity scan + checkpoint recovery →
sentinel-2/-3 re-seed → kafka-exporter start → fresh 24h stability clock → MW2
re-assessment from zero.

---

## Recovery Complete + 48h Observation Window — 2026-06-24T11:35Z

Operator confirmed host hardening (datastore-level **write-through + barriers**,
no longer unsafe writeback) and performed a **clean reboot** (fresh boot
2026-06-24 11:03:55Z; **no soft lockups / RCU stalls** this boot — vs 24 such
lines on the prior boot). Recovery was then executed and completed.

### What recovered
- **redis master + replica:** torn-tail AOFs fixed (`redis-check-aof --fix`,
  1,178 bytes each); replica re-synced from master; replication link up.
- **sentinel-2/-3:** corrupt configs cleared, re-seeded from the clean git
  template; all 3 sentinels healthy (`ckquorum OK`).
- **kafka:** no backup existed (MinIO/wal-archive hold only PostgreSQL PITR), so
  **KRaft metadata was reformatted (option A), reusing `cluster.id`
  5L6g3nShT-eMCtK--X86sw**. Broker came up clean (`Kafka Server started`); app
  re-created `diep.commands` + `__consumer_offsets`.
- **kafka-exporter:** started, scraping (`kafka_brokers 1`).
- All 7 critical services + 3 sentinels healthy, `restarts=0`.

### PERMANENT data loss (on record — not erased by a clean window)
- **redis:** 1,178-byte torn tail on master (replica re-synced → no independent loss).
- **kafka (reformat):** `diep.commands` message backlog (~28 KB), all
  `__consumer_offsets` consumer positions, and topic configs — **unrecoverable**.
  cluster.id preserved; topics re-created empty.
- TimescaleDB / MinIO / redis dataset otherwise intact.

### Observation window — EXTENDED to 48h
- **Basis:** 2026-06-24T11:29:15Z (latest critical container StartedAt; not reset).
- **Target:** **2026-06-26T11:29:15Z** (extended from 24h → **48h** for this first
  post-hardening cycle — the failure mode only manifests on unclean resets, so one
  calm 24h is weak evidence the fix holds against that trigger).
- Clock resets if any critical container restarts before the target.

### Decisions held (unchanged)
**MW2 = NO-GO · Production = DENIED · DO-NOT-GO-LIVE** until the 48h window
completes clean **and** a fresh MW2 host assessment passes. No release tag until then.
Any restart or corruption symptom (torn AOF tail, foreign block-reuse content,
KRaft metadata error) before the target is to be treated as a durability-fix
recurrence and flagged immediately.
