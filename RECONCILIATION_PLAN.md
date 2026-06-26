# DIEP Release 1.0 — Reconciliation Plan

**Date:** 2026-06-26. Covers Phase 2 (functional mapping) and Phase 3
(merge strategy) of the Branch Reconciliation Sprint, plus the Phase 4
conflict-area review, ahead of executing the actual merge.

---

## Phase 2 — Functional mapping

### Branch A (`feature/adms-topology-import`) — all 3 commits

| Commit | Purpose | Dependencies | Production impact today | Belongs in Release 1.0? |
|---|---|---|---|---|
| `8bab151` | New `topology/` CLI package (GeoJSON/CIM parser + loader) and `POST /topology/versions` in `fastapi/routers/topology.py`, the first writer of a second `network_model_versions` row. | `sql/013`'s existing `network_model_versions`/`grid_nodes`/`grid_edges` tables (already on `main`, both branches). | **Not live** — `diep-fastapi` runs Branch B's code, which lacks this endpoint (confirmed: live `404` on both `GET`/`POST /topology/versions`). The standalone `topology/` CLI isn't containerized either way, so it's usable today regardless of which branch `fastapi` runs. | **Yes** — explicitly named in the sprint's success criteria ("Topology Import"). |
| `c1b52fc` | `sql/024` — idempotent `setval()` fix for `network_model_versions`'s sequence, which never advanced past the `sql/013` seed row. | Needs `8bab151`'s importer/endpoint to actually be exercised (nothing else writes a second version). | Schema-only, safe to apply anytime; **already applied live** but not yet exercised (sequence at 1, only 1 row exists) — see `BRANCH_DIFFERENCE_REPORT.md` §9. | **Yes** — same rationale. |
| `d411dcc` | `sql/025` — additive, nullable `network_model_version` column on 5 audit-relevant tables (`flisr_events`, `control_actions`, `control_audit`, `outage_cases`, `automation_events`); wires `common.current_model_version()` into the write path of `automation.py`, `controls.py`, `dms.py`, `oc_flisr.py`, `oms.py`. | `8bab151`'s `network_model_versions` semantics. | Schema **already applied live** (confirmed via direct query). Stamping code **not live** (Branch B's routers don't have it). | **Yes** — same rationale. |

### Branch B (`release/v1.0-rc-qualification`) — all 33 commits, grouped

Every commit is listed in full in `BRANCH_DIFFERENCE_REPORT.md` §3; grouped
here by subsystem for purpose/impact assessment (re-litigating each
individually would just restate that list — the qualification and audit
reports already on this branch are themselves the purpose/impact record for
most of these).

| Group | Commits | Purpose | Production impact today | Belongs in Release 1.0? |
|---|---|---|---|---|
| DLMS/COSEM driver | `acada0c`, `cd51a4f`, `c21bcad`, `991b689`, `b4a5367` | Hand-rolled DLMS/COSEM client + simulator + HDLC transport, stdlib-only. | Dormant library code, not bind-mounted into any of the 31 running containers; exercised only by its own tests/simulator. Per its own `drivers/dlms/VALIDATION.md`, not yet validated against real hardware. | **Yes** — named in success criteria; explicitly scoped as a library, not a regression risk to the live stack. |
| Production hardening | `0cca472`, `5fa449b` | Closes the zero-backup gap; adds freshness/replication alert rules and the textfile-collector metric pattern. | **Live**, partially — see `FINAL_RELEASE_RECOMMENDATION.md` §3 for the still-open host-cron gap this audit found. | **Yes** — named in success criteria ("Production Hardening"). |
| AMI/MDM/OPC UA pipeline | `73158b7`, `9bae526`, `470a3fc`, `869749c`, `e77ec73` | Canonical telemetry contract, MDM quality/enrichment service, OPC UA connector, SIT findings and the stabilization fixes that followed. | **Live** — `diep-mdm`, `diep-opcua-connector`, `diep-ingestor` all confirmed correctly worktree-sourced in the prior audit. | **Yes** — named in success criteria. |
| CIM/IEC 61968 | `eb5e6a8`, `5e0e81f` | Read-only REST adapter exposing the platform's data as CIM-shaped resources. | **Live** — `diep-cim` confirmed correctly worktree-sourced. | **Yes** — named in success criteria. |
| RC qualification | `acf5020` … `98eff36` (14 commits) | Performance, capacity, HA, soak, security review, and the 8 RC deliverable documents. | Documentation/test-script artifacts; no running-code change by themselves. | **Yes** — named in success criteria ("Qualification work"). |
| Security & deployment-source fixes | `6d1ba30`, `da253af`, `965fdfb`, `03e5a54`, `a1fd5f3`, `8180a20` | Closes the `/telemetry/latest` auth gap; finds and fixes the `diep-fastapi`/`diep-node-exporter` wrong-checkout bug; corrects a false backup-monitoring finding. | **Live** — `diep-fastapi`'s auth fix is active and tested; see `FINAL_RELEASE_RECOMMENDATION.md` §2 for the one functional cost of this group's `fastapi` recreation (the topology-endpoint regression this sprint exists to fix). | **Yes** — named in success criteria ("Security fixes", "Deployment Audit"). |
| Configuration & Deployment Audit | `0c69d69` | Full 31-container inventory, drift report, recreates `prometheus`/`wal-shipper`/`grafana`/`redis-exporter` from the worktree, release manifest. | **Live** — all 4 recreations verified in place. | **Yes** — named in success criteria ("Deployment Audit"). |

**No commit on either branch is recommended for exclusion.** This matches
the sprint's explicit success criteria, which names every one of these
subsystems as required in Release Candidate 2.

---

## Phase 3 — Reconciliation strategy

Given `BRANCH_DIFFERENCE_REPORT.md`'s findings — zero overlapping commits,
zero file-level conflicts, zero deletions/renames, zero migration-number
collisions — the strategy is uniform and simple:

**Strategy: standard `git merge`, once, in one direction.**

Not cherry-pick (no reason to rewrite 3 clean, well-documented commits as
something else), not manual reconciliation (nothing to reconcile by hand —
there's no overlapping content to arbitrate), not reimplementation (the
code already exists and works; reimplementing it would violate the
sprint's own "preservation, not simplification" framing).

**Direction:** create `release/v1.0-rc2` from `release/v1.0-rc-qualification`
(Branch B — the far larger, already-qualified history) and merge
`feature/adms-topology-import` (Branch A — the much smaller, 3-commit
branch) into it. Merging the other direction would require rebuilding
Branch B's entire qualification/audit trail on top of Branch A's tiny
history for no benefit — Branch B is the natural integration trunk here.

Expected result: a single 3-way merge commit, zero conflict markers,
verified below in Phase 4/5 before being trusted.

---

## Phase 4 — Conflict-area review (named areas from the sprint brief)

| Area | Touched by Branch A? | Touched by Branch B? | File-level conflict? | Notes |
|---|---|---|---|---|
| FastAPI | Yes (`common.py` + 6 routers) | Yes (`app.py`, `auth.py`, other routers) | **No** — disjoint file sets within `fastapi/`. | Closest thing to a risk area: same service, adjacent files. Topology.py already imports `auth.require_role` (pre-existing on `main`); Branch B never changes that import contract, so no functional clash expected — verified live in Phase 5. |
| Topology | Yes (sole owner) | No | No | Pure addition; nothing to reconcile. |
| Authentication | No | Yes (sole owner) | No | Branch A's router uses the auth module as-is; doesn't modify it. |
| Audit logging | Yes — but a **different "audit"**: `network_model_version` stamping on `control_audit`/`flisr_events`/etc. (data lineage) | Yes — `auth.audit()` writing to `audit_events` (security access log) | No — different tables, different module, no shared code. | Naming proximity only; flagged explicitly here so it isn't mistaken for overlap during validation. |
| Deployment scripts | No | Yes (sole owner) | No | |
| Prometheus | No | Yes (sole owner, incl. this sprint's own audit work) | No | |
| Grafana | No | Yes (sole owner) | No | |
| Backup monitoring | No | Yes (sole owner) | No | The still-open host-cron gap (`FINAL_RELEASE_RECOMMENDATION.md` §3) is internal to Branch B; merging Branch A doesn't change it either way. |
| WAL shipper | No | Yes (sole owner) | No | |
| MQTT | No | Yes (sole owner) | No | |
| Docker Compose | No | Yes (sole owner) | No | Branch A adds no service and changes no compose file — `diep-fastapi`'s compose definition is unaffected by this merge. |
| Cron jobs | No | Yes (sole owner) | No | |

Every named area resolves to "no conflict" except FastAPI, which resolves
to "no file conflict, one functional integration point worth testing
explicitly" — done in Phase 5, not assumed clean just because git says so.
