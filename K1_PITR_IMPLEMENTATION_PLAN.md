# K1 — PostgreSQL/TimescaleDB Point-In-Time Recovery (PITR)
## Implementation Plan

**Phase:** 17, Stage 1 (K1 — highest priority in the Phase 17 HA roadmap)
**Status:** Design + side-by-side validation (no production changes yet)
**Author:** Senior Platform Architect (DIEP)
**Date:** 2026-06-15

---

## 1. Objective

Replace the current nightly `pg_dump`-only backup strategy (RPO ≈ 24h) with
continuous WAL archiving to MinIO, enabling point-in-time recovery (PITR) to
any second between base backups. This is the prerequisite for K2 (full
PostgreSQL HA via CloudNativePG, `k8s/postgres-cnpg.yaml`), which already
assumes `backup.barmanObjectStore` + continuous WAL archiving exists.

---

## 2. Current State Assessment

| Item | Current value | Source |
|---|---|---|
| Engine | `timescale/timescaledb:latest-pg16`, container `diep-timescaledb` | `docker-compose.yml` |
| `wal_level` | `replica` (already sufficient for archiving — **no change needed**) | live `SHOW wal_level` |
| `archive_mode` | `off` | live `SHOW archive_mode` |
| `archive_command` | `(disabled)` | live `SHOW archive_command` |
| `max_wal_size` | `1GB` (default) | live `SHOW max_wal_size` |
| Logical backups | Nightly `pg_dump -Fc` via `scripts/backup-db.sh`, cron 02:00, uploaded to MinIO bucket `diep-backups`, 14-day retention, verified weekly by `scripts/verify-backup.sh` | `scripts/backup-db.sh`, `scripts/install-backup-cron.sh` |
| Object storage | MinIO container `diep-minio`, network `diep-lab_diep-net`, already used for backups | `docker-compose-minio.yml` |
| RPO today | ≈ 24h (time since last successful `pg_dump`) | nightly cron only |
| RTO today | ~Time to provision a new TimescaleDB container + `pg_restore` of the latest dump (typically 10-20 min for current DB size) | derived from `restore-db.sh` / `verify-backup.sh` |

**Key finding:** `wal_level=replica` is already correct for both streaming
replication (K2) and archiving (K1) — this is a configuration-only change on
top of the existing engine, with no schema or application changes.

---

## 3. Target Design

### 3.1 WAL Archiving Strategy

Two-stage "stage-then-ship" pipeline, chosen so the PostgreSQL container does
**not** need an S3/MinIO client baked into its image (the stock
`timescale/timescaledb` image has no `mc`/`aws` binary):

```
┌─────────────────────────┐   archive_command    ┌──────────────────┐   mc mirror (15s loop)   ┌────────────────────┐
│ diep-timescaledb         │ ───────────────────▶ │ /wal-archive/      │ ───────────────────────▶ │ MinIO                │
│ (archive_mode=on)         │  cp %p → staging     │ (shared volume)    │  staged WAL → bucket     │ diep-wal-archive/    │
└─────────────────────────┘                       └──────────────────┘                          └────────────────────┘
                                                                                                    diep-pg-basebackups/
```

- **`archive_command`** copies each completed WAL segment into a local
  shared volume (`wal-archive`), refusing to overwrite an existing file
  (standard PostgreSQL idempotency contract for `archive_command`).
- **`wal-shipper` sidecar** (the `minio/mc` image, already used by
  `backup-db.sh`) runs `mc mirror` against that shared volume on a short
  interval, pushing newly staged segments to the MinIO bucket
  `diep-wal-archive` and pruning shipped segments locally once confirmed.
- **`archive_timeout = 60`** forces a WAL segment switch at least every 60s
  even during low write activity, bounding RPO to ~60s + shipping interval
  (≈ 75s worst case) regardless of transaction volume.

### 3.2 Configuration Changes (target, applied to validation first)

| Setting | Current | Target | Rationale |
|---|---|---|---|
| `wal_level` | `replica` | `replica` (unchanged) | already sufficient |
| `archive_mode` | `off` | `on` | enable WAL archiving |
| `archive_command` | `(disabled)` | `test ! -f /wal-archive/%f && cp %p /wal-archive/%f` | stage WAL segments for shipping |
| `archive_timeout` | `0` (disabled) | `60` | bound RPO during idle periods |
| `max_wal_size` | `1GB` | `1GB` (unchanged) | no evidence of checkpoint pressure; revisit under K2 |
| `restore_command` (recovery only) | n/a | `cp /restore-archive/%f %p` (with a pre-recovery `mc mirror` pull from `diep-wal-archive`) | fetch archived segments during PITR |

### 3.3 Base Backups

- Add a **weekly `pg_basebackup`** (in addition to the existing nightly
  `pg_dump`) using `pg_basebackup -D - -Ft -z -Xs | upload to
  s3://diep-pg-basebackups/<timestamp>.tar.gz`.
- `pg_dump` (logical, per-table) is **retained unchanged** — it remains the
  fast path for single-table/application-level restores and is independent
  of WAL archiving.
- `pg_basebackup` + WAL archive together form the **physical PITR chain**:
  restore the most recent base backup, then replay WAL up to the desired
  `recovery_target_time`.

### 3.4 MinIO Bucket Layout

| Bucket | Contents | Retention |
|---|---|---|
| `diep-backups` (existing) | Nightly `pg_dump` logical backups | 14 days (unchanged) |
| `diep-wal-archive` (new) | WAL segments (`000000010000...`) | 7 days (covers ≥1 base backup interval + margin) |
| `diep-pg-basebackups` (new) | Weekly `pg_basebackup` tarballs | 4 weeks |

### 3.5 PITR Recovery Procedure (target runbook)

1. Provision a fresh PostgreSQL data directory from the most recent
   `diep-pg-basebackups` tarball.
2. `mc mirror` the WAL segments from `diep-wal-archive` (from the base
   backup's start WAL onward) into a local `restore-archive` directory.
3. Create `recovery.signal` in the data directory.
4. Set `restore_command = 'cp /restore-archive/%f %p'` and
   `recovery_target_time = '<YYYY-MM-DD HH:MM:SS UTC>'`.
5. Start PostgreSQL; it replays WAL until the target time, then pauses (with
   `recovery_target_action = 'pause'`) so an operator can verify data before
   promoting (`pg_wal_replay_resume()` / promote).

---

## 4. Implementation Steps (this stage)

1. ✅ Assess current configuration (Section 2).
2. ✅ Design WAL archiving strategy (Section 3).
3. Build a **side-by-side validation stack** (`docker-compose-pitr-validation.yml`):
   a throwaway TimescaleDB container (`diep-pg-pitr-val`, separate volume,
   separate port) + `wal-shipper` sidecar, both attached to the existing
   `diep-lab_diep-net` so the shipper can reach `diep-minio`.
4. Configure `archive_mode=on`, `archive_command`, `archive_timeout=60` on
   the validation container only.
5. Validate the full lifecycle end-to-end (Section 5 / see
   `K1_PITR_VALIDATION_REPORT.md`):
   - base backup creation,
   - WAL archive generation + shipping to MinIO,
   - point-in-time restore to a chosen timestamp,
   - recovery and data verification.
6. **Only after validation passes**, schedule the production change as a
   follow-up maintenance task (Section 6) — **not executed in this stage**.

---

## 5. Validation Plan (side-by-side, isolated from production)

- New container `diep-pg-pitr-val` (image `timescale/timescaledb:latest-pg16`,
  fresh named volume `pitr-val-data`, port `5433`, throwaway credentials) —
  **completely separate from `diep-timescaledb`/`timescale-data`**.
- New sidecar `diep-pg-pitr-wal-shipper` (image `minio/mc`) on
  `diep-lab_diep-net`, shipping to **new** buckets `diep-wal-archive` /
  `diep-pg-basebackups` (separate from production's `diep-backups`).
- Test sequence:
  1. Start stack, confirm `archive_mode=on`.
  2. Create a test table, insert "BEFORE" rows, record timestamp **T1**.
  3. Take a `pg_basebackup`, upload to `diep-pg-basebackups`.
  4. Insert "AFTER" rows, force a WAL switch (`pg_switch_wal()`), confirm the
     segment lands in `diep-wal-archive` via the shipper.
  5. Stop the container, discard its data volume (simulating total loss).
  6. Restore from the base backup + replay WAL with
     `recovery_target_time = T1`.
  7. Verify: "BEFORE" rows present, "AFTER" rows absent → proves recovery to
     an arbitrary point between writes.
  8. Tear down the entire validation stack and volumes; production
     (`diep-timescaledb`, `diep-backups`) is untouched throughout.

Results are recorded in `K1_PITR_VALIDATION_REPORT.md`, including measured
RPO/RTO before vs. after.

---

## 6. Production Rollout (deferred — not part of this stage)

Only after `K1_PITR_VALIDATION_REPORT.md` shows PASS for all four checks:

1. Create MinIO buckets `diep-wal-archive` and `diep-pg-basebackups` in the
   production MinIO instance.
2. Add a `wal-shipper` sidecar service to `docker-compose.yml` (mirrors the
   validated sidecar config), sharing a new `wal-archive` named volume with
   `diep-timescaledb`.
3. Apply the three `postgresql.conf` changes from Section 3.2 to
   `diep-timescaledb` via `ALTER SYSTEM SET ...; SELECT
   pg_reload_conf();` (no restart required for `archive_mode`... **note**:
   `archive_mode` actually requires a restart — schedule during the next
   maintenance window).
4. Add a weekly `pg_basebackup` job alongside the existing
   `install-backup-cron.sh` entries.
5. Run `verify-backup.sh`-style drill against the new WAL/base-backup chain
   monthly, in addition to the existing weekly logical-restore drill.

---

## 7. Rollback Procedure

**Production is not modified in this stage**, so no rollback is required for
the validation work itself. For the deferred production rollout (Section 6),
rollback is a config revert with no data-loss risk:

| Step | Rollback action |
|---|---|
| `archive_mode=on` | `ALTER SYSTEM SET archive_mode = 'off'; ALTER SYSTEM SET archive_command = ''` then restart `diep-timescaledb` (next maintenance window) |
| `wal-shipper` sidecar | Remove the service from `docker-compose.yml`; `wal-archive` volume can be deleted once confirmed unneeded |
| New MinIO buckets | Leave in place (idempotent, no impact) or remove with `mc rb` |
| Existing `pg_dump` cron / `diep-backups` | **Untouched throughout** — remains the fallback recovery path at all times |

Because the existing nightly logical-backup pipeline is never disabled or
modified, the system can fall back to the pre-K1 recovery path (RPO ≈ 24h) at
any point without data loss.

---

## 8. RPO / RTO Summary

| | Before (current) | After (K1 target) |
|---|---|---|
| **RPO** | ≈ 24h (time since last `pg_dump`) | ≈ 60-75s (`archive_timeout` + shipping interval) |
| **RTO** | ~10-20 min (provision + `pg_restore` of logical dump) | Base-backup restore (minutes, dominated by data volume size) + WAL replay (seconds per WAL segment since base backup) — measured in `K1_PITR_VALIDATION_REPORT.md` |

Measured values from the validation run are recorded in
`K1_PITR_VALIDATION_REPORT.md`.
