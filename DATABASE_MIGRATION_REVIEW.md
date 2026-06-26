# DIEP Release 1.0 — Database Migration Review (Phase 2)

**Date:** 2026-06-26. Determines whether `sql/021_network_electrical.sql`
should be applied before the `diep-fastapi` cutover or deferred. **No
migration is applied as part of this review** — decision and rationale
only, per this phase's explicit instruction.

---

## What `sql/021` does

`ALTER TABLE grid_nodes ADD COLUMN IF NOT EXISTS phases VARCHAR(3) NOT NULL
DEFAULT 'ABC';` and the equivalent for `grid_edges`, plus `UPDATE` statements
backfilling `phases`/`base_load_kw`/`base_load_kvar`/`load_class` for a
fixed list of named seed nodes/edges (`SUB-ABUJA`, `FDR-01`, `TX-01`,
`TX-02`, `BUS-01`, `ND-METER001`, etc.) and resistance/reactance/length/
ampacity values for named seed edges.

Committed on `main` itself — inherited unchanged by **both**
`feature/adms-topology-import` and `release/v1.0-rc-qualification`/
`release/v1.0-rc2`. Not new from any branch in this reconciliation; not
something either branch's authors added independently.

## Corrected finding: this is not a dormant gap, it is an active production bug

`RC2_VALIDATION_REPORT.md` originally (incorrectly) stated this migration
gap only affects the standalone bulk-importer CLI. Re-checked directly
against the **live, currently-running, pre-cutover** `diep-fastapi`
(still on `release/v1.0-rc-qualification`, untouched by anything in this
sprint) using a freshly-minted admin token:

| Endpoint | Result, live, right now |
|---|---|
| `GET /topology/validate` | **500 Internal Server Error** |
| `GET /topology/adjacency` | **500 Internal Server Error** |
| `GET /topology/graph` | 200 (uses `SELECT *`, doesn't reference `phases` by name, masks the gap) |
| `POST /topology/nodes` | Not fired live (avoided writing test data into the shared DB) — confirmed by source inspection that its `INSERT` column list includes `phases`; would fail the same way. |
| `POST /topology/edges` | Same as above, by inspection. |
| `POST /topology/versions` (this sprint's headline restoration) | **Unaffected** — only touches `network_model_versions`, never `grid_nodes`/`grid_edges`. |

This means two of `topology.py`'s pre-existing read endpoints are already
broken in production today, independent of this cutover, this
reconciliation, or anything else in this engagement — they have been
broken since whenever the live database was first provisioned without
`sql/021` ever being run against it.

## Decision: **apply before cutover**

Rationale:

1. **Already broken regardless of the cutover decision.** Deferring
   doesn't preserve a working state — there is no working state for
   `/topology/validate`/`/topology/adjacency` today. Deferring only delays
   a fix to an existing problem.
2. **Low risk.** `ADD COLUMN IF NOT EXISTS ... NOT NULL DEFAULT 'ABC'` is
   additive and idempotent by construction — it cannot fail against a
   database that doesn't already have a conflicting `phases` column (it
   doesn't), and it does not touch any other table or any code path this
   cutover is concerned with.
3. **No dependency on which branch `fastapi` runs.** Both
   `release/v1.0-rc-qualification` and `release/v1.0-rc2` contain the
   `phases`-referencing code (it's inherited from `main`); applying this
   migration helps the *currently live* container immediately, before any
   cutover happens, and continues to help after.
4. **The seed-data `UPDATE` statements target specific named nodes**
   (`SUB-ABUJA`, `FDR-01`, etc.) that may or may not exist in this live
   database's actual `grid_nodes` rows (this review did not enumerate the
   live row set to confirm). If they don't exist, those specific `UPDATE`
   statements are no-ops (zero rows matched) — not an error — so this does
   not change the safety conclusion, only means the seed backfill may be
   partially inapplicable to this specific database's actual content.

**This was not executed as part of this review** — applying a schema
change to the shared live database is being surfaced as its own explicit
decision point, consistent with how database-affecting actions have been
handled throughout this engagement (e.g. the `.env`/live-password
reconciliation, the backup-failure-simulation request), not bundled
silently into a larger sprint. See `FINAL_RELEASE_DECISION.md` for how this
is carried forward.
