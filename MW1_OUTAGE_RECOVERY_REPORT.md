# MW1 Outage Recovery Report

**Incident:** MW1 PITR WAL Staging Leak
**Date:** 2026-06-18
**Severity:** SEV-1 (database down, production-impacting)
**Detected during:** MW1 48-hour soak
**Outage window:** ~2026-06-18 09:20Z (shipping stalled / disk full) → 10:24Z (PostgreSQL accepting connections)
**Recovery verified:** 2026-06-18 10:25Z

---

## 1. Root Cause Analysis

The MW1 PITR implementation (commit `0ceb9e7`) shipped a WAL archiving pipeline whose
shipper (`wal-shipper/ship-wal.sh`) **mirrored** WAL segments from the local staging
volume (`diep-lab_wal-archive`) to MinIO but **never deleted the local staging copies
after a confirmed upload**. `K1_PITR_IMPLEMENTATION_PLAN.md` §3.1 explicitly required
"pushing newly staged segments to the MinIO bucket **and pruning shipped segments
locally once confirmed**" — the prune step was omitted (carried over verbatim from the
validation script `pitr-validation/scripts/ship-wal.sh`, which also lacked it).

With `archive_timeout = 60`, PostgreSQL forces a 16 MiB WAL segment switch every minute
(~1 GB/hour) regardless of write volume. Each segment is copied into `/wal-archive` by
`archive_command` and was never removed, so staging grew without bound until the 48 GB
root filesystem reached 100%. PostgreSQL could then no longer write its own `pg_wal`
during crash recovery and entered a restart loop:

```
FATAL:  could not write to file "pg_wal/xlogtemp.NN": No space left on device
```

This is a regression introduced by the MW1 change. The failure mode only manifests under
sustained runtime (hours), which the point-in-time failover/shipping drill at cutover did
not exercise — a gap in the original MW1 verification, now corrected by Phase 6 below
(sustained ship+prune validation) and the staging-size retention alarm.

---

## 2. Phase 1 — Evidence Collection (pre-change, @ 2026-06-18T10:15Z)

| Signal | Value |
|---|---|
| Root filesystem | `48G` size, `46G` used, **`0` available, 100%** |
| WAL staging volume (`diep-lab_wal-archive`) | **4.8 GB**, 309 WAL segments |
| PostgreSQL (`diep-timescaledb`) | `Status=restarting`, `RestartCount=26`, `ExitCode=1` (crash loop) |
| FastAPI `/readyz` | `{"ready": false, "checks": {"database": false, "redis": true}}` |
| MinIO `diep-wal-archive` objects | 281 (279 × 16 MiB WAL segments + 2 `.backup` label files) |
| Redis Sentinel | healthy, master `172.18.0.240:6379`, quorum 2/2 (unaffected throughout) |

### Set arithmetic — the deletion-safety basis

| Set | Count | Meaning |
|---|---|---|
| Local 24-char WAL segments | 309 | everything `archive_command` had staged |
| MinIO 24-char WAL segments | 279 | confirmed uploaded |
| **Local ∩ MinIO (SAFE TO DELETE)** | **279** | exists locally **and** confirmed in MinIO at full 16 MiB |
| **Local − MinIO (MUST KEEP)** | **30** | staged but not yet uploaded — contiguous newest tail `00000001000000010000001F` → `...013C` (shipping stalled here when the disk filled) |

Each of the 279 safe-delete segments was independently re-verified present in MinIO **at
the full 16 MiB size** (0 partial/truncated objects). The 30 unshipped segments were
preserved — deleting them would risk a PITR gap, since once `archive_command` reports
success PostgreSQL may recycle its own `pg_wal` copy, leaving the staging copy as the
only surviving one until MinIO ingests it.

> **Verification-reliability note:** an initial set-arithmetic query returned "0 MinIO
> segments" due to a shell-quoting bug (`\$NF` mangled inside nested quotes), not a MinIO
> fault. Because the verify-before-delete rule is absolute, this was caught and corrected
> before any deletion; the intersection was recomputed from a clean MinIO listing and
> cross-checked by object size. No deletion was ever attempted against an unverified list.

---

## 3. Phase 2 — Safe Recovery (disk reclamation)

A deletion manifest of the 279 confirmed segments was built and guarded three ways at
execution time: (1) each name must be a 24-char hex segment, (2) each must be absent from
the unshipped keep-list (mounted read-only into the deletion container), (3) the file must
exist. PostgreSQL was stopped first to halt restart-loop churn.

| Result | Value |
|---|---|
| Segments deleted | **279** (exactly the confirmed set) |
| Segments remaining | **30** (exactly the unshipped keep-set) |
| Disk before → after | 100% (0 free) → **91% (4.4 GB free)** |
| Unshipped segments touched | **0** |

---

## 4. Phase 5 (executed early) — Permanent Fix

**Sequencing decision:** the shipper fix was deployed *before* restarting PostgreSQL.
Restarting Postgres onto the still-leaking shipper would merely restart the countdown to
the same outage, so the fix was front-loaded. The fixed shipper then also drained the 30
unshipped segments cleanly while no new segments were being generated — an ideal closed
test of the prune path.

`wal-shipper/ship-wal.sh` was rewritten from `mc mirror` (no prune) to an
**upload → verify → prune** loop. A segment is deleted **only** after: (a) `mc cp`
succeeds (checksum-verified transfer), (b) `mc stat` confirms the object exists in MinIO,
and (c) the local file size is unchanged across the upload (guards against pruning a
half-written segment mid-`archive_command`). Any failure keeps the local copy for the next
cycle. Verification uses `mc` **exit codes only** — the `minio/mc` image is minimal and has
no `grep`/`awk`/`sed` (this was caught live: a first rewrite using `grep` to parse sizes
failed, and the fail-safe correctly **kept all 30 segments, zero data loss**, proving the
contract). A 2 GiB staging-size alarm was added as an early-warning so the leak can never
silently recur even if MinIO becomes unreachable.

Diff and rollback plan are in §8.

---

## 5. Phase 3 — PostgreSQL Recovery

| Check | Result |
|---|---|
| `pg_isready` | OK (first attempt) |
| Container status | `running`, `RestartCount=0` |
| Query (`select now()`) | returns `2026-06-18 10:24:48Z` |
| `archive_mode` | `on` |
| TimescaleDB | continuous-aggregate refresh resumed normally in logs |

PostgreSQL completed its interrupted crash recovery (idempotent WAL replay) on the first
start once disk space existed, and came up clean.

---

## 6. Phase 4 — FastAPI Recovery

| Check | Result |
|---|---|
| `curl http://localhost:8000/readyz` | `{"ready": true, "checks": {"database": true, "redis": true}}` |

FastAPI reconnected to the database on its own (per-request `psycopg2` connections); no
restart was required.

---

## 7. Phase 6 — Validation (sustained pipeline, with PostgreSQL live)

| Check | Result |
|---|---|
| 30 unshipped segments shipped+pruned | ✅ drained to 0 in <24s (`shipped=32 pruned=32 kept=0`, incl. 2 `.backup` files) |
| Formerly-unshipped tail now in MinIO | ✅ `...1F` and `...3C` both `PRESENT` (PITR chain continuous, nothing lost) |
| New WAL (forced `pg_switch_wal()` ×2 with PG live) | ✅ shipper logged `shipped=7 pruned=7`, then `shipped=1 pruned=1` |
| Staging stays bounded | ✅ **0 segments** across 45s of observation post-switch |
| MinIO object count | grew 317 → 318 (new segments landing) |
| Disk | stable at **93%** (no growth) |
| All 26 containers | `Up`; Redis Sentinel quorum 2/2 |

The defining symptom (unbounded staging growth) is gone: with PostgreSQL actively
generating segments, staging now returns to 0 every cycle.

---

## 8. Phase 5 detail — Code Diff, Explanation, Rollback

**Explanation:** see §4. The change is confined to `wal-shipper/ship-wal.sh` (the
sidecar's entrypoint script); no compose, schema, or application change is involved. The
script is mounted read-only into `diep-wal-shipper` and takes effect on container
recreate.

**Rollback plan:** `git checkout 0ceb9e7 -- wal-shipper/ship-wal.sh` then
`docker compose up -d --no-deps --force-recreate wal-shipper` restores the previous
behavior. This is **not recommended** — the previous behavior is the defect — but the
prior version remains available in history if needed. Because the new script never deletes
an unconfirmed segment, the worst-case failure of the new code is the *old* behavior
(staging grows), now bounded by the 2 GiB alarm, not data loss.

---

## 9. Soak Status

**MW1 SOAK INVALIDATED.** A SEV-1 regression (this incident) was discovered during the
soak window; the soak cannot count time accumulated while the platform was unstable /
down.

**New soak start:** 2026-06-18 10:25Z (recovery verification).
**New soak end / earliest MW2 eligibility:** **2026-06-20 10:25Z** (48 hours from verified
recovery), conditional on the staging-size alarm staying quiet and disk usage remaining
flat for the duration.

---

## 10. Verdict

**CONDITIONAL GO** (recovery only — *not* an MW2 authorization).

- The outage is resolved, root cause is fixed at the source, and the fix is validated live
  under PostgreSQL load.
- PITR integrity was preserved end-to-end: every deleted segment was confirmed in MinIO
  first; the 30 unshipped segments were retained and have since shipped, so the archive
  chain is continuous with no gap.
- The "conditional" is the fresh 48-hour soak: MW2 (K6 MinIO HA) remains **NOT** authorized
  until 2026-06-20 10:25Z with a clean soak.
- Carry-forward risk (pre-existing, unrelated to this incident): security findings F1/F2/F3/F4
  in `SECURITY_REMEDIATION_PLAN.md` remain open, and the training-doc set plus this report
  are uncommitted until the commit step.
