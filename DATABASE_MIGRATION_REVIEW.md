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

---

## Addendum, 2026-06-26 (Final Release Closure, Phase 1) — full schema-change/
rollback/maintenance-window detail, ahead of actually applying it

### Exact schema changes (full statement-by-statement review)

1. `ALTER TABLE grid_nodes DROP CONSTRAINT IF EXISTS
   grid_nodes_node_type_check;` + `ADD CONSTRAINT ... CHECK (node_type IN
   (...9 values including 'recloser'...))` — **widens** the original
   8-value check (from `sql/013`) to 9 values. Strictly a superset: every
   value the old constraint allowed, the new one still allows, plus
   `'recloser'`. No existing row can violate it (if it satisfied the old,
   narrower constraint, it satisfies the new, wider one).
2. 4 new columns on `grid_nodes`: `phases VARCHAR(3) NOT NULL DEFAULT
   'ABC'`, `base_load_kw REAL NOT NULL DEFAULT 0`, `base_load_kvar REAL
   NOT NULL DEFAULT 0`, `load_class VARCHAR(32)` (nullable, no default).
3. 5 new columns on `grid_edges`: `resistance_r_ohm`, `reactance_x_ohm`,
   `length_km`, `ampacity_a` (all `REAL`, nullable, no default), `phases
   VARCHAR(3) NOT NULL DEFAULT 'ABC'`.
4. 9 `UPDATE` statements against `grid_nodes`, 10 against `grid_edges`,
   each scoped to a specific, named `node_id`/`edge_id` (the Abuja Site A
   pilot's own seed data — `SUB-ABUJA`, `FDR-01`, `TX-01`, `TX-02`,
   `BUS-01`, `ND-METER001`, `ND-BAT001`, `ND-INV001`, `ND-EV001`,
   `ND-MG001`, `ND-MGD900`, and the matching `E-*` edges). These are the
   exact same node/edge IDs already observed live via `GET /topology/graph`
   in this engagement's prior validation — confirmed to exist, so these
   `UPDATE`s are expected to actually match rows, not be no-ops.

### Backward compatibility

All four statement types are additive-only: a widened `CHECK` constraint,
new columns with safe defaults or nullable, and `UPDATE`s scoped to
specific existing rows (never an `INSERT`, never a `DELETE`, never a `DROP`
of anything). No existing query, row, or constraint can be broken by this
migration — confirmed by construction (it is written `IF NOT EXISTS`/
`IF EXISTS` throughout, matching this repo's own established `sql/000..020`
idempotency convention per the migration's own header comment).

### Rollback procedure (not part of `sql/021` itself — written here since
none exists in the repo)

```sql
ALTER TABLE grid_nodes DROP COLUMN IF EXISTS phases;
ALTER TABLE grid_nodes DROP COLUMN IF EXISTS base_load_kw;
ALTER TABLE grid_nodes DROP COLUMN IF EXISTS base_load_kvar;
ALTER TABLE grid_nodes DROP COLUMN IF EXISTS load_class;
ALTER TABLE grid_edges DROP COLUMN IF EXISTS resistance_r_ohm;
ALTER TABLE grid_edges DROP COLUMN IF EXISTS reactance_x_ohm;
ALTER TABLE grid_edges DROP COLUMN IF EXISTS length_km;
ALTER TABLE grid_edges DROP COLUMN IF EXISTS ampacity_a;
ALTER TABLE grid_edges DROP COLUMN IF EXISTS phases;
ALTER TABLE grid_nodes DROP CONSTRAINT IF EXISTS grid_nodes_node_type_check;
ALTER TABLE grid_nodes ADD CONSTRAINT grid_nodes_node_type_check
    CHECK (node_type IN ('substation','feeder','transformer','switch',
                         'bus','meter','der','load'));
```
Dropping the columns removes the seeded values along with the columns —
acceptable for a rollback (the goal is reverting to the pre-migration
state, not preserving seed data the migration itself introduced). This
would, in turn, re-break `GET /topology/validate`/`GET /topology/adjacency`
back to their current (already-broken) state — a rollback restores the
status quo, it does not introduce a new regression.

### Production impact (restated precisely)

Net effect of applying: fixes two currently-500ing endpoints
(`GET /topology/validate`, `GET /topology/adjacency`), unblocks
`POST /topology/nodes`/`POST /topology/edges` and the standalone bulk
importer CLI, and backfills electrical metadata for the existing Abuja
Site A pilot seed rows that the data model already expected but never
received. No endpoint or behavior that currently works goes from working
to broken.

### Maintenance window

This environment has no formal change-management/maintenance-window
tooling — there is no calendar, ticket system, or CI gate to "approve" a
window against. The explicit, written instruction to apply this migration
now, combined with this being a single-operator lab/pilot deployment with
no other concurrent users of `diep-timescaledb` (confirmed throughout this
engagement — every prior action affecting this database was performed and
observed by this same session, with no evidence of concurrent external
write activity), is treated as the approval and **now** as the window.
Applying immediately after this review is written, with the live system's
behavior captured before and after, in `PRODUCTION_CUTOVER_REPORT.md`'s
successor for this sprint.
