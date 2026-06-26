# DIEP Release 1.0 — Merge Preparation (Phase 8)

**Status: prepared, not executed.** Per this sprint's explicit instruction,
none of the actions below (merge, tag) have been run. This document exists
so that when the user gives the explicit go-ahead, the merge is a single
reviewed action rather than something assembled under time pressure.

---

## 1. Merge plan

```
git checkout main
git pull --ff-only            # confirm main hasn't moved since 238a70e
git merge --no-ff release/v1.0-rc2
```

- **Source:** `release/v1.0-rc2` @ `595829e75b6d82b7c10b1fbedc189f528bc3e1a4`
  (worktree `.claude/worktrees/rc2-reconciliation`).
- **Target:** `main` @ `238a70ef1f391c57588fccadcc784525683e6d0a` (unchanged
  since this whole engagement began — confirmed no one else has moved it).
- **Expected result:** fast-forward is *not* possible (rc2 and main share
  only the `238a70e` ancestor, rc2 has 38 commits beyond it) — this will be
  a real merge commit. Given everything already merged cleanly going *into*
  rc2 (`BRANCH_DIFFERENCE_REPORT.md`: zero conflicts), and main itself
  hasn't moved, this merge is expected to be a trivial fast-forward-shaped
  merge in content even though git represents it as a merge commit (main's
  tree is `rc2`'s own ancestor with nothing added independently).
- **Recommend `--no-ff`** (explicit merge commit, not squash) so the full,
  already-detailed commit history (qualification, security fixes,
  deployment audit, branch reconciliation, production cutover) remains
  individually visible and bisectable in `main`'s history, consistent with
  how this entire engagement has preferred new commits over rewriting
  history.

## 2. Tag message (draft)

```
git tag -a v1.0.0 -m "$(cat <<'EOF'
DIEP v1.0.0

First tagged production release. Combines:
- Platform recovery and production hardening
- AMI contract, DLMS/COSEM driver, MDM, OPC UA connector
- CIM/IEC 61968 read-only adapter
- ADMS topology import (GeoJSON/CIM bulk loader, POST /topology/versions,
  network-model-version audit stamping)
- Release Candidate qualification (performance, capacity, HA, soak,
  security review)
- Security remediation (GET /telemetry/latest auth + tenant scoping)
- Configuration & Deployment Audit (deployment-source-integrity gate)
- Branch reconciliation (feature/adms-topology-import +
  feature/dlms-driver, merged via release/v1.0-rc2)
- Production cutover of diep-fastapi to the reconciled branch

Known limitations at this tag, not blocking but not resolved: sql/021's
"phases" column not yet applied to the live database (breaks
GET /topology/validate and GET /topology/adjacency; does not affect
POST /topology/versions); operational-interface authentication
(Prometheus/Alertmanager/kafka-ui/cAdvisor/Node-RED) still open; backup
freshness metric not yet wired to the actual cron-scheduled backup once
main absorbs this work (needs a follow-up crontab repoint); Redis
replication and single-broker Kafka unresolved; host write-durability
defect and production hardware sizing still pending. See
KNOWN_LIMITATIONS.md for the full, current list.

See FINAL_RELEASE_DECISION.md for the evidence behind this release.
EOF
)"
```

## 3. Merge summary (for the PR description / commit message, if this
repository uses either)

> Merges `release/v1.0-rc2` into `main`, closing out the DIEP v1.0
> qualification → security remediation → deployment audit → branch
> reconciliation → production cutover sequence run across this engagement.
>
> **What's new on `main` after this merge:** everything previously only on
> `feature/dlms-driver`/`release/v1.0-rc-qualification` (DLMS driver, MDM,
> OPC UA, CIM, qualification, security fixes, deployment audit) *and*
> everything previously only on `feature/adms-topology-import` (GeoJSON/CIM
> topology importer, `POST /topology/versions`, network-model-version audit
> stamping) — combined, validated together, with zero file-level conflicts
> and zero functional regression in either direction (see
> `RC2_VALIDATION_REPORT.md`, `PRODUCTION_CUTOVER_REPORT.md`).
>
> **What this merge does not do:** apply the pending `sql/021` migration
> (a live database change, deliberately left as a separate, explicit
> decision — see `DATABASE_MIGRATION_REVIEW.md`); repoint the production
> crontab at `main` post-merge (the backup-monitoring host-cron gap's actual
> fix, also deliberately separate); or close any of the longer-standing
> operational gaps already tracked in `KNOWN_LIMITATIONS.md`.

## 4. Rollback point

Already recorded in `FINAL_RELEASE_DECISION.md`. Restated here for this
specific merge action:

- **If the merge itself needs to be undone** (before pushing/sharing):
  `git reset --hard 238a70e` on `main` (recovers exactly the pre-merge
  state; no data/schema changes are tied to the merge commit itself).
- **If the live `diep-fastapi` container needs to be rolled back**
  (independent of the git-level merge decision): recreate it from
  `release/v1.0-rc-qualification` @ `2dd9763`
  (`.claude/worktrees/dlms-driver-validation`) with the same
  `--force-recreate` pattern used for the cutover — no data migration
  either direction, confirmed in `PRODUCTION_CUTOVER_REPORT.md`.
- **The tag `v1.0.0`**, once created, should not be deleted/moved if
  already pushed/shared — if a rollback is needed after the tag is public,
  cut a `v1.0.1` rather than rewriting `v1.0.0`'s history, consistent with
  this engagement's "create new commits, don't rewrite" discipline.

---

## What is required before this is run (not assessed in this document —
listed so the next step is a decision, not a surprise)

1. Explicit user authorization to actually execute the merge and tag —
   neither has been done.
2. A decision on `sql/021` (apply or formally accept as deferred) — doesn't
   block the merge technically, but should be a conscious choice made
   before or shortly after, not forgotten.
3. A decision on consolidating the two currently-live RC worktrees
   (`dlms-driver-validation`, `rc2-reconciliation`) — again, not a merge
   blocker, but worth doing before either worktree is removed or this
   becomes its own confusion later.
