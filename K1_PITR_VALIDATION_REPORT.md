# K1 — PostgreSQL/TimescaleDB PITR Validation Report

**Phase:** 17, Stage 1 (K1)
**Date:** 2026-06-15
**Environment:** Side-by-side validation stack (`docker-compose-pitr-validation.yml`,
project `diep-pitr-val`), entirely separate containers/volumes from production.
**Production impact:** **None.** `diep-timescaledb` was never stopped,
reconfigured, or restarted. Confirmed `archive_mode=off` on production
before and after this test (unchanged).

---

## 1. Summary

| Check | Result |
|---|---|
| Base backup creation | ✅ PASS |
| WAL archive generation + shipping to MinIO | ✅ PASS |
| Point-in-time restore to a selected timestamp | ✅ PASS |
| Recovery to a selected timestamp (data verification) | ✅ PASS |

**Overall: PASS.** The design in `K1_PITR_IMPLEMENTATION_PLAN.md` is validated
end-to-end and is ready to be scheduled for production rollout
(`K1_PITR_IMPLEMENTATION_PLAN.md`, Section 6).

---

## 2. Test Environment

- `diep-pg-pitr-val` — `timescale/timescaledb:latest-pg16`, fresh volume
  `pitr-val-data`, port 5433, started with `wal_level=replica`,
  `archive_mode=on`, `archive_timeout=60`, and
  `archive_command='test ! -f /wal-archive/%f && cp %p /wal-archive/%f'`.
- `diep-pg-pitr-wal-shipper` — `minio/mc` sidecar, shared `wal-archive`
  volume, attached to `diep-lab_diep-net`, mirroring to MinIO every 5s into
  new buckets `diep-wal-archive` and `diep-pg-basebackups` (created for this
  test, removed afterward — see Section 7).
- Confirmed config live on the validation instance:

  ```
  archive_mode    = on
  archive_command = test ! -f /wal-archive/%f && cp %p /wal-archive/%f
  archive_timeout = 1min
  wal_level       = replica
  ```

---

## 3. Test Sequence and Results

### 3.1 Base backup creation — ✅ PASS

- Created table `pitr_test`, inserted 3 "BEFORE" rows.
- Recorded PITR target timestamp **T1 = `2026-06-15 10:44:01.146996+00`**.
- Ran `pg_basebackup -Ft -z -Xs` → produced `base.tar.gz` (4.53 MiB),
  `pg_wal.tar.gz` (16.7 KiB), `backup_manifest` (218 KiB).
- Uploaded all three to MinIO bucket `diep-pg-basebackups`.

### 3.2 WAL archive generation + shipping — ✅ PASS

- Fixed a permissions issue found during setup: the shared `wal-archive`
  volume was created root-owned by the `minio/mc` sidecar; `postgres` (uid
  70) could not write to it, causing `archive_command` to fail
  (`Permission denied`, logged and retried per PostgreSQL's standard
  archiver retry behavior — **no WAL was lost**, archiving simply queued).
  Fixed with `chown postgres:postgres /wal-archive`. **This is now a
  documented prerequisite for the production rollout** (Section 6 of the
  implementation plan must `chown` the production `wal-archive` volume to
  the `postgres` uid before enabling `archive_mode`).
- Inserted 2 "AFTER" rows (`AFTER-1`, `AFTER-2`), then `pg_switch_wal()`.
- Within ~10s, 5 WAL artifacts appeared in `/wal-archive` and were mirrored
  to `m/diep-wal-archive`:
  - `000000010000000000000001` … `000000010000000000000004` (16 MiB each)
  - `000000010000000000000003.00000028.backup` (the base-backup label file)

### 3.3 Point-in-time restore to a selected timestamp — ✅ PASS

- Stopped and discarded `diep-pg-pitr-val` (simulating total data loss).
- Restored `base.tar.gz` into a fresh volume, `chown`'d to uid 70.
- Downloaded WAL segments 1-4 from `diep-wal-archive` into a
  `restore-archive` volume.
- Added `recovery.signal` + `postgresql.auto.conf`:
  ```
  restore_command      = 'cp /restore-archive/%f %p'
  recovery_target_time = '2026-06-15 10:44:01.146996+00'
  recovery_target_action = 'pause'
  ```
- Started a new container against the restored volume.

### 3.4 Recovery to a selected timestamp — ✅ PASS

Postgres log (annotated):

```
10:49:17.535  starting point-in-time recovery to 2026-06-15 10:44:01.146996+00
10:49:17.588  restored log file "000000010000000000000003" from archive
10:49:17.642  restored log file "000000010000000000000004" from archive
10:49:17.667  consistent recovery state reached at 0/3000138
10:49:17.667  database system is ready to accept read-only connections
10:49:17.669  recovery stopping before commit of transaction 766, time 2026-06-15 10:46:50.082635+00
10:49:17.669  pausing at the end of recovery
```

While paused at T1 (read-only):

| id | label | created_at |
|---|---|---|
| 1 | BEFORE-1 | 10:43:50 |
| 2 | BEFORE-2 | 10:43:50 |
| 3 | BEFORE-3 | 10:43:50 |

`AFTER-1`/`AFTER-2` (committed at 10:46:50, **after** T1) were correctly
**excluded** — PostgreSQL's recovery engine stopped exactly before that
transaction's commit, as requested.

After `pg_wal_replay_resume()` (promote):

- `pg_is_in_recovery()` → `f` (writable primary).
- Data unchanged: still exactly the 3 BEFORE rows.

---

## 4. RPO / RTO — Before vs. After

| | Before (current) | After (K1, measured) |
|---|---|---|
| **RPO** | ≈ 24h (nightly `pg_dump` only) | **≈ 60s** (`archive_timeout=60`) + ≈5s shipping interval ⇒ **worst case ≈ 65s** of data at risk. In this test, the WAL segment containing the test transaction was archived and shipped to MinIO within **~10s** of `pg_switch_wal()`. |
| **RTO** | ~10-20 min (provision container + `pg_restore` of ~MB-GB logical dump, current DB size) | **Restore-to-target-time: 0.13s** (10:49:17.535 → 10:49:17.667, "consistent recovery state reached") for this dataset; **promotion: ~12s** (10:49:17.669 → 10:49:29.279). End-to-end container start → writable primary at target time ≈ **12 seconds** for this dataset. Production RTO will scale with base-backup size and WAL volume to replay, but the *mechanism* overhead is sub-15s. |

These figures confirm the design assumptions in
`K1_PITR_IMPLEMENTATION_PLAN.md` Section 8.

---

## 5. Issues Found and Resolved

1. **`/tmp/basebackup` not visible via `--volumes-from`** — `pg_basebackup`
   output written to the container's ephemeral filesystem (`/tmp`) is not
   shared via Docker named volumes. Resolved by `docker cp` to host before
   upload. *No production impact — the production rollout will write
   `pg_basebackup` output directly to a shared volume or stream it via a
   pipe, avoiding this step.*
2. **WAL archive volume permissions** — see Section 3.2. Documented as a
   prerequisite step for the production rollout.

Neither issue caused data loss or required any production change.

---

## 6. Recommendation

K1 design is **validated and ready for production scheduling**. Proceed with
`K1_PITR_IMPLEMENTATION_PLAN.md` Section 6 (Production Rollout) during the
next maintenance window, noting the added prerequisite:

> Before setting `archive_mode=on` on `diep-timescaledb`, `chown` the new
> `wal-archive` volume to the `postgres` container's uid (70) so
> `archive_command` succeeds on the first attempt.

`archive_mode` requires a PostgreSQL restart to take effect — bundle this
with the next planned maintenance window restart.

---

## 7. Cleanup Performed

- Removed containers `diep-pg-pitr-val`, `diep-pg-pitr-wal-shipper`,
  `diep-pg-pitr-restore`.
- Removed volumes `diep-pitr-val_pitr-val-data`, `diep-pitr-val_wal-archive`,
  `diep-pitr-val_restore-data`, `diep-pitr-val_restore-archive`.
- Emptied and removed temporary MinIO buckets `diep-wal-archive` and
  `diep-pg-basebackups` (created for this test only).
- Removed local scratch directory `/tmp/pitr-basebackup`.
- Production buckets `diep-backups` and `diep-config-backups` untouched.
- `docker-compose-pitr-validation.yml` and `pitr-validation/scripts/ship-wal.sh`
  are retained in the repo as the validated reference implementation for the
  production rollout.
