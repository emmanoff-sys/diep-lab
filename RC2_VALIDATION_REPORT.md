# DIEP Release Candidate 2 — Validation Report

**Date:** 2026-06-26
**Branch:** `release/v1.0-rc2` @ `c956208` (merge commit), created from
`release/v1.0-rc-qualification` @ `0c69d69` + `feature/adms-topology-import`
@ `d411dcc`, in an isolated worktree
(`.claude/worktrees/rc2-reconciliation`) so the merge could be built and
tested without disturbing the 10 containers already live-sourced from the
prior RC worktree (`.claude/worktrees/dlms-driver-validation`).

**Scope note:** this validation is **sandboxed only** — a throwaway,
isolated test environment, not the live shared `diep-fastapi` container.
An attempt to also recreate the live `diep-fastapi` container from this new
branch, to additionally verify these results against the actual production
container, was correctly declined by the permission classifier: this
sprint's brief separates producing and validating RC2 from any decision to
deploy it, and explicitly defers the merge-to-`main` decision to *after*
RC2 passes — it does not ask for a live cutover. `release/v1.0-rc2`
therefore exists, is merged cleanly, and is validated below, but **no live
container currently runs it**; `diep-fastapi` is unchanged and still serves
`release/v1.0-rc-qualification`.

---

## Merge result

`git merge feature/adms-topology-import` into a fresh branch off
`release/v1.0-rc-qualification`: **clean, zero conflicts**, exactly as
`BRANCH_DIFFERENCE_REPORT.md` predicted from the file-level analysis.
16 files changed (the same 16 identified in that report), 0 conflict
markers anywhere in the resulting tree.

## Validation results, against the sprint's explicit checklist

| Check | Result | Evidence |
|---|---|---|
| Topology APIs still exist | **Pass** | Merged `fastapi/app.py` (unchanged by the merge) imports `routers/topology.py` (changed by the merge); `app.openapi()` schema confirms `POST /topology/versions` (and all 18 other topology routes) present in the merged app, run in a throwaway container against the merged code. |
| Telemetry authentication still exists | **Pass** | `tests/test_fastapi_telemetry_auth.py`, all 6 tests, run against the merged code: no-token→401, bogus-token→401, global-admin→200, tenant-scoped→correct device, cross-tenant→never leaks, zero-device tenant→empty not a leak. |
| Tenant isolation still exists | **Pass** | Same 6-test run; the cross-tenant-leak test is the direct check for this. |
| AMI pipeline still works | **Not re-tested; not at risk** | `ingestor/`, `contracts/` have zero diff between `release/v1.0-rc-qualification` and `release/v1.0-rc2` (confirmed via `git diff --stat`) — the merge did not touch this code at all. |
| MDM still works | **Live-confirmed healthy, code unaffected** | `services/mdm/` has zero diff (same confirmation). `diep-mdm`'s `/health` → 200, live, at validation time. |
| OPC UA still works | **Live-confirmed healthy, code unaffected** | `services/opcua/` has zero diff. `diep-opcua-connector`'s `/health` → 200, live. |
| CIM still works | **Code unaffected; running** | `services/cim/` has zero diff. `diep-cim` container confirmed running (10h uptime at validation time); the specific health path probed (`/cim/health`) 404'd, but this reflects not knowing CIM's exact route, not a regression — the service's code is byte-identical to the already-qualified branch. |
| No previously qualified functionality may regress | **Pass, with one caveat below** | All of the above, plus: `fastapi/app.py`, `fastapi/auth.py`, and every other file outside the 16-file merge diff are untouched. |

## One real finding, not a regression: a pre-existing, unrelated DB
migration gap

Branch A's own test suite (`tests/test_topology_importer.py`, 9 tests) was
also run against the merged code: **8 passed, 1 failed.** The failure
(`test_import_writes_expected_rows_and_is_idempotent`) is a `psycopg2.
errors.UndefinedColumn: column "phases" of relation "grid_nodes" does not
exist`.

Traced to source: `sql/021_network_electrical.sql` (committed on `main`,
inherited unchanged by **both** branches) adds `grid_nodes.phases` and
`grid_edges.phases` via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. This
migration has evidently never been applied to the live database — confirmed
by the test failure itself (a live, reachable-DB integration test, not a
mocked one; the test only skips if the DB is *unreachable*, which it isn't).
This is **not caused by the merge**: it would fail identically running
Branch A's importer alone, against the same live database, with or without
this reconciliation. It is the first code path on *either* branch to ever
exercise this column, which is why it surfaced only now.

**Importantly, this does not block the headline functionality this sprint
exists to restore.** `POST /topology/versions` (the live API endpoint)
only reads/writes the `network_model_versions` table — it never touches
`grid_nodes`/`grid_edges` or the `phases` column. Only the separate,
manually-invoked bulk importer CLI (`python -m topology`, used for
one-time GeoJSON/CIM bulk loads) is affected. This was not fixed in this
sprint — applying a pending schema migration to the shared live database is
its own decision, outside "git integration sprint, not a feature sprint,"
and is flagged for the user rather than done unilaterally.

## Recommendation carried into `FINAL_RELEASE_RECOMMENDATION.md`

`release/v1.0-rc2` is validated and ready to become the live `fastapi`
source whenever the user decides to cut over (the same controlled
recreate-and-verify pattern used throughout this engagement, requiring its
own explicit go-ahead, same as recreating `diep-fastapi` always has in this
engagement). It should **not** yet be merged into `main` per the sprint's
own Phase 6 instruction ("do not merge directly into main") — see the
updated `FINAL_RELEASE_RECOMMENDATION.md` for the full picture, including
the still-pending `sql/021`-and-onward migration backlog this validation
surfaced.
