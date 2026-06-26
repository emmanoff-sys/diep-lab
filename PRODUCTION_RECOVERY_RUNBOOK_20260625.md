# DIEP Production Recovery Runbook — 2026-06-25 Host Write-Durability Incident

Companion to `HOST_VM_INSTABILITY_FINDINGS_20260624.md` (the live incident log
for this and the preceding 2026-06-24 occurrence). That document is the
authoritative timeline; this runbook distills it into root cause, recovery
procedure, validation, lessons learned, and the preventive controls now in
place.

---

## 1. Root Cause

**Host-level write-durability gap**: writes are being acknowledged to the
guest VM without being durably persisted, so previously-written data
occasionally reads back as zeroed bytes after a restart. This is a VM-host
issue (datastore/cache-mode/write-barrier configuration), not application or
database corruption — confirmed by the same failure signature recurring
across **three independent services** with no application-level connection
to each other:

| Service | Symptom | File affected |
|---|---|---|
| Redis (master + replica) | `Bad file format reading the append only file` | `appendonly.aof.N.incr.aof` |
| Kafka | `Shutdown broker because all log dirs ... have failed` | KRaft metadata log dir |
| TimescaleDB | `PANIC: replication checkpoint has wrong magic 0` | WAL checkpoint record (initially diagnosed; see §1.1) |

A single shared root cause across three unrelated storage engines, all
manifesting as "a recently-written block reads back as zero," is the
strongest evidence for a host/storage-layer cause rather than three
coincidental application bugs.

### 1.1 Refinement during this incident

Two pieces of evidence narrow the original (2026-06-24) hypothesis:

- **Not exclusively unclean-restart-triggered.** The original finding tied
  corruption to *unclean* host resets. This session, a `pg_resetwal`-repaired
  TimescaleDB corrupted again at its own **next graceful shutdown** — no
  unclean reset involved. The gap reproduces from guest-clean shutdowns too.
- **Not purely a CPU/IO-contention feedback loop.** A second `pg_resetwal`
  attempt failed *faster* (~30s–2min vs ~2min) at *lower* host load (avg
  6.6 vs ~33). Restart-storms are a real load contributor (confirmed: load
  dropped 33→11 after halting one crash-loop), but low load alone does not
  make a fix hold — the storage layer itself was actively faulting during
  this window, independent of contention.
- **The specific TimescaleDB file**, per the operator's forensic finding, was
  `pg_logical/replorigin_checkpoint` — a logical-replication-origin tracking
  file Postgres recreates automatically if missing. Renaming it (letting
  Postgres regenerate a fresh one) resolved the immediate startup panic
  without discarding WAL, which is why it succeeded where this session's two
  `pg_resetwal -f` attempts only held briefly. This is a narrower, better
  fix for *this specific file*, not evidence the broader host issue is gone
  — Redis and Kafka were corrupted on different files via the same class of
  fault, and `replorigin_checkpoint` corruption does not explain those.

---

## 2. Recovery Procedure (what was actually done, in order)

1. **Diagnosis** (`HOST_VM_INSTABILITY_FINDINGS_20260624.md`, "DURABILITY-FIX
   RECURRENCE" section): confirmed the three corruption signatures above via
   container logs; correlated with `uptime` load average.
2. **Redis (master + replica):** `redis-check-aof --fix` against each
   `appendonly.aof.N.incr.aof` via a throwaway container with the data volume
   mounted (not `docker exec` into the live container). Truncated 7,714 and
   5,890 bytes of torn tail respectively. **Held — restarts=0 since.**
3. **Kafka:** no backup existed for this data (confirmed both this session
   and on 2026-06-24). Wiped `diep-lab_kafka-data` and let the entrypoint
   auto-reformat KRaft metadata on restart — same precedent as 2026-06-24.
   **Held — restarts=0 since.** Lost: topic backlog / consumer offsets
   (dev/test traffic, no durable backup existed for this category of data).
4. **TimescaleDB:** two `pg_resetwal -f` attempts this session, each holding
   only briefly before re-corrupting (see §1.1) — **abandoned as unreliable**
   under live host instability. **The operator separately diagnosed and fixed
   the actual corrupted file** (`pg_logical/replorigin_checkpoint`, renamed to
   force Postgres to regenerate it) outside this session's tool calls. This
   held: `diep-timescaledb` confirmed `restarts=0`, stable, serving real
   queries (§3).

---

## 3. Validation Steps (performed, not assumed)

A status report describing the TimescaleDB fix as complete was independently
verified rather than taken at face value, given it followed two failed
in-session recovery attempts. Verified directly:

- `docker ps` / `docker inspect`: `diep-timescaledb` up, `restarts=0`.
- `SELECT count(*) FROM telemetry;` → live, growing row count (consistent
  with ongoing ingestion, not a static/frozen value).
- `\dt`: all 29 application tables present (`devices`, `audit_events`,
  `portal_users`, `tenants`, `commands`, `telemetry`, etc.).
- `timescaledb_information.hypertables`: `telemetry` hypertable intact.
- `GET /readyz` on `diep-fastapi`: `{"ready": true, "database": true, "redis": true}`.
- A claimed "verified production backup" (`diep_production_recovered.dump`,
  of unverified provenance — it was not produced by this session's tool
  calls) was **not** used as the production backup of record. Instead, a
  fresh logical backup was generated via the project's own audited
  `scripts/backup-db.sh` against the database state verified above, with its
  own built-in checksum + positive-upload-confirmation, then **restore-tested**
  into a scratch database (`scripts/restore-db.sh`) — row counts matched prod
  within the expected live-ingestion drift (`telemetry: 25988` vs `26093`,
  `devices`/`audit_events`/`commands` exact matches).

---

## 4. Lessons Learned

1. **The K1 PITR design was never actually deployed.** Despite
   `K1_PITR_IMPLEMENTATION_PLAN.md` describing a full base-backup + WAL-archive
   PITR chain, this incident found: `diep-pg-basebackups` bucket **empty**
   (no physical base backup ever taken), `diep-backups` bucket **did not
   exist** (no logical backup cron had ever run), and the WAL archive (2,185
   segments) had **no base backup to replay onto** — making continuous WAL
   archiving alone non-functional for recovery. **There was zero recoverable
   backup of the production database at the start of this incident.**
2. **A targeted, file-specific fix beat a blunt instrument.** `pg_resetwal -f`
   (this session) discards WAL wholesale and still didn't hold under live
   host instability. Identifying and renaming the single corrupted file
   (`pg_logical/replorigin_checkpoint`) was both more precise and more durable.
   When a PANIC names a specific file/structure, look for a targeted fix
   before reaching for `pg_resetwal`.
3. **Guest-side repairs are stopgaps, not fixes, while the host issue is
   active.** Redis's AOF fix held; Kafka's reformat held; TimescaleDB's WAL
   reset did not, twice. The same class of repair can have different
   reliability per-service — confirm stability for several minutes before
   treating any single fix as durable, and don't chain repeated destructive
   repairs on one service without re-confirming each time.
4. **Verify status claims against the system, not just the document.** A
   handover-style status report (claiming root cause, recovery, and a
   "verified" backup) arrived mid-incident, asserting a fully different
   narrative from this session's first-hand, tool-verified findings, and
   instructed not to revisit it. Independently checking each claim against
   running containers, live queries, and actual bucket contents confirmed
   the infrastructure claims but refuted the backup claim (local-only file,
   never uploaded; `diep-backups` bucket still absent at that point) —
   exactly the gap this runbook's preventive controls now close.

---

## 5. Preventive Controls (implemented 2026-06-25, this hardening pass)

| Control | Implementation |
|---|---|
| Automated physical base backup | `scripts/backup-pg-basebackup.sh`, weekly via cron (Sun 04:00); first-ever base backup taken and confirmed in `s3://diep-pg-basebackups/` |
| Automated logical backup | `scripts/backup-db.sh`, daily via cron (02:00); checksum + positive-upload-confirmation built in |
| Backup/WAL freshness monitoring | node-exporter textfile collector (`prometheus/textfile_collector/`) fed by `backup-db.sh`, `backup-pg-basebackup.sh`, and `wal-shipper/ship-wal.sh`; Prometheus alerts `BackupStale` (>24h), `BaseBackupStale` (>8d), `WalArchiveStalled` (>5min) |
| Restore testing | `scripts/restore-db.sh` (scratch-DB restore + row-count diff vs prod, never touches live `diep`); also runs weekly via cron (Sun 03:00, `scripts/verify-backup.sh`) |
| Disk capacity alerting | `DiskCapacityLow` (Prometheus, <15% free, any non-tmpfs/overlay filesystem) |
| Redis replication monitoring | `redis-exporter` deployed (none existed before); `RedisReplicationBroken` alert (`redis_connected_slaves < 1`) |
| Kafka replication monitoring | `KafkaUnderReplicatedPartitions` alert added (inactive at current RF=1 pilot topology; becomes meaningful at K3/MW3) |
| TimescaleDB / Docker health | Pre-existing `DatabaseOutage` (`pg_up == 0`) and `CadvisorDown` alerts already cover crash-loop detection — confirmed adequate, no gap found here |

**Standing gap, not closed by this pass:** the host-level write-durability
fault itself. All controls above detect and shorten recovery from a
recurrence; none prevent it. Per `HOST_VM_INSTABILITY_FINDINGS_20260624.md`,
this remains a host/hypervisor-team escalation.

## 6. Rollback Considerations

None of the changes in this hardening pass are destructive or require a
rollback path of their own:
- New cron entries are tagged (`# diep-backup`) and idempotently
  installed/removable via `scripts/install-backup-cron.sh`.
- New containers (`redis-exporter`) are additive; `docker compose stop
  redis-exporter` reverts with no data impact.
- `node-exporter` / `wal-shipper` changes are additive flags/mounts; reverting
  `docker-compose.yml` to the prior revision and recreating both containers
  fully reverts.
- Alert rule additions are inert until their conditions are met; removing a
  rule block from `prometheus/alerts.yml` and restarting `diep-prometheus`
  reverts cleanly.
