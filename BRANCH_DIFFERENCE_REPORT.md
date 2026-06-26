# DIEP Release 1.0 — Branch Difference Report

**Date:** 2026-06-26
**Method:** `git merge-base`, `git log <base>..<branch>`, `git diff --name-status`,
and `git patch-id` between `main`, `feature/adms-topology-import` (Branch A),
and `release/v1.0-rc-qualification` (Branch B, the `feature/dlms-driver`
lineage) — no assumptions carried over from prior sessions.

---

## 1. Topology

`main` tip: `238a70e`. Both branches forked from `main` at this exact
commit and never merged with each other or back into `main`.

```
                 8bab151 c1b52fc d411dcc
                /---o-------o-------o   feature/adms-topology-import (Branch A, 3 commits)
main 238a70e --*
                \---o--- ... ---o (14)---o--- ... ---o (18) --- 0c69d69
                 feature/dlms-driver      release/v1.0-rc-qualification
                                          (Branch B, 14+18 = 32 commits over dlms-driver)
```

## 2. Commits unique to Branch A (`feature/adms-topology-import`) — 3

| Commit | Summary |
|---|---|
| `8bab151` | Phase 2 (topology import): GeoJSON/CIM importer + publish-version endpoint |
| `c1b52fc` | sql/024: fix network_model_versions sequence never advancing |
| `d411dcc` | Phase 4 (topology import): stamp network_model_version on audit tables |

## 3. Commits unique to Branch B (`release/v1.0-rc-qualification`) — 33

(14 on `feature/dlms-driver` itself, 19 added by the qualification/
remediation/audit work on top of it — 33 total vs. `main`.)

```
acada0c Phase 1 step 1 (dlms): minimal DLMS/COSEM simulator + protocol/transport
cd51a4f Phase 1 step 2 (dlms): DlmsMeterClient + driver adapter + integration tests
c21bcad Phase 1 step 3 (dlms): harden association/error paths + validation caveat
b4a5367 docs(planning): record integration-gap roadmap decision (OPC UA/MDM/CIM)
991b689 Phase 2 (dlms): HDLC interface transport (SNRM/UA) + isolated unit tests
0cca472 docs: record 2026-06-25 durability-fix recurrence; add OPC UA discovery notes
5fa449b Production hardening: close zero-backup gap, add freshness/replication alerts
73158b7 Phase 4 (ami-ingest): pin canonical MQTT/Kafka telemetry contract
9bae526 Add MDM (Meter Data Management) service
470a3fc OPC UA connector Phases 1-3: framework, subscriptions, security
869749c SIT: end-to-end OT->IT validation (pre-CIM) -- verdict: NOT READY FOR CIM
e77ec73 Post-SIT stabilization sprint: fix NaN loss, async ingestor, wire MDM+OPC UA into production path
eb5e6a8 Add CIM/IEC 61968 interoperability layer as a read-only REST adapter
5e0e81f Fix CIM_INTEROPERABILITY_REPORT.md: correct fabricated 68/68 check count to verified 81/81
acf5020 RC qualification: re-confirm performance baseline, add steady-state latency
0851b11 RC qualification: capacity planning raw data (host resources, Prometheus history, telemetry sizing)
37ee5c9 RC qualification: Redis Sentinel failover drill (real kill, not restart)
411b0f7 RC qualification: re-confirm HA restart recovery (FastAPI/MQTT/Kafka/Timescale) + new Portal test
b186251 RC qualification: soak workstream backup-completion check finds two real gaps
89f1392 RC qualification: security review -- live-confirmed findings
f31a218 RC qualification: draft 6 of 8 RC deliverables (qualification report, limitations, guides)
ab5349d RC qualification: add GO_LIVE_CHECKLIST.md (7 of 8 RC deliverables)
6995bc1 RC qualification: rewrite RELEASE_NOTES_v1.0.md as RC baseline superseding 06-13
5604e49 RC qualification: soak test results -- 30 min @ ~12 msg/s, zero loss, no corruption
a4bdfd4 RC qualification: finalize soak section and verdict -- RELEASE CANDIDATE APPROVED WITH LIMITATIONS
98eff36 RC qualification: add missing soak_load.py script and raw output
6d1ba30 Security remediation: require auth + tenant scoping on GET /telemetry/latest
da253af Document and fix: diep-fastapi was bind-mounted from the main checkout, not the RC worktree
965fdfb Document telemetry-auth closure + deployment-source bug + permanent release gate
03e5a54 KNOWN_LIMITATIONS.md: mark /telemetry/latest auth gap closed, for consistency
a1fd5f3 Correct a false qualification finding: backup monitoring was already wired, not missing
8180a20 Add FINAL_RELEASE_VALIDATION.md: RELEASE APPROVED WITH LIMITATIONS
0c69d69 Configuration & Deployment Audit: full inventory, drift report, Category C reconciliation, release manifest
```

## 4. Overlapping commits

**None.** Confirmed by `git patch-id` comparison across both unique sets —
zero shared patch IDs. The two branches share only their common ancestor
history; no commit was cherry-picked or independently reproduced on both
sides.

## 5. Conflicting files

**None, at the file level.** `git diff --name-only main <branch>` for each
branch, intersected:

- Branch A touches 16 files (7 modified, 9 newly created).
- Branch B touches 210 files (16 modified, 194 newly created).
- **Intersection: empty set.** No file is touched by both branches' unique
  commits.

Branch A's 7 modified files (`fastapi/common.py`, `fastapi/routers/
{automation,controls,dms,oc_flisr,oms,topology}.py`) are all in
`fastapi/`, a directory Branch B's qualification/security work also
touches extensively (`app.py`, `auth.py`, `routers/cim.py`, etc.) — but
never these specific 6 files. This is the closest thing to a risk area in
this whole comparison (same directory, adjacent files, same general
subsystem) and is called out specifically in `RC2_VALIDATION_REPORT.md`
even though no textual conflict exists.

This means a standard `git merge` of either branch into the other (or both
into a new integration branch) is expected to apply with **zero textual
merge conflicts**. See `FINAL_RELEASE_RECOMMENDATION.md` (this report's
companion) for why "no conflicts" does not mean "no risk" — see §6 below
for the one substantive cross-branch interaction found.

## 6. Deleted files

**None on either branch.** `git diff --summary` against `main` shows only
`create mode` and modification lines for both branches — no `delete mode`
entries.

## 7. Renamed files

**None detected on either branch** (no R-status entries in
`git diff --name-status`).

## 8. SQL migration numbering

Branch A adds `sql/024_topology_version_seq_fix.sql` and
`sql/025_audit_network_model_version.sql`. Branch B's highest migration is
`sql/023_production_cutover.sql`. **No numbering collision** — Branch B
never created a 024 or 025, so Branch A's migrations slot in immediately
after Branch B's without renumbering.

## 9. Live database state (checked directly, not assumed)

Queried the running `diep-timescaledb` via a throwaway `psql` container:

- All 5 `network_model_version` columns from `sql/025`
  (`flisr_events`, `control_actions`, `control_audit`, `outage_cases`,
  `automation_events`) **already exist on the live database** — someone
  (consistent with Branch A's commits being from earlier today) has
  already applied this migration directly against the shared database,
  independent of which branch's `fastapi` container is running.
- `network_model_versions` has exactly 1 row (`version=1, is_current=true`,
  the `sql/013` seed row) and its backing sequence (`sql/024`'s target) is
  still at `last_value=1` — i.e., `sql/024`'s underlying bug has not yet
  been *triggered* (nothing has published a second version), so its fix
  hasn't been exercised live, but is also not contradicted by anything live.
- **Consequence:** the database schema is currently ahead of the
  application code actually running (`diep-fastapi`, sourced from Branch B,
  has no code path that uses these columns or the `POST /topology/versions`
  endpoint that would write them). This is additional, independent
  confirmation of the same finding from the prior Configuration &
  Deployment Audit (`FINAL_RELEASE_RECOMMENDATION.md` §2) — not a new
  contradiction, but it raises the practical urgency: the schema change is
  not hypothetical or pending, it is live and currently unused.

---

## Summary

This is, structurally, about the cleanest possible branch-divergence
scenario: two sibling branches, zero overlapping commits, zero file-level
conflicts, zero deletions, zero renames, zero migration-number collisions.
The risk in reconciling them is not git-mechanical — `git merge` will not
itself produce a single conflict marker. The risk is **functional**: Branch
A's 3 commits modify files that Branch B's separately-evolved `fastapi/`
service must now run alongside, and that combination has never been tested
together. See `RC2_VALIDATION_REPORT.md` for that validation.
