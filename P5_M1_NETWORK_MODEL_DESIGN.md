# DIEP ADMS P5-M1 — Network Model Service — Design & Validation

**Phase:** 23 (P5 Advanced DMS Foundation) · **Module:** M1 — Network Model Service
**Branch:** `feature/adms-p5-advanced-dms` · **Status:** implemented + validated (isolated DB)
**Classification:** additive, read-mostly. No control plane, no flags, no breaking changes.

---

## 1. Objective

Turn the M1 *connectivity* model (sql/013 — nodes/edges, good enough for OMS
affected-customer walks and FLISR switching) into a full **electrical** network
model that the P5 analytics layer can solve on:

- per-edge **series impedance** (R/X), length, **ampacity**, and **phasing**;
- per-node **phasing** and **base load** (kW/kvar);
- a first-class **`recloser`** node type alongside the existing switch/tie edges;
- **topology validation**: orphan detection, source check, parent/edge hierarchy
  consistency, and **loop detection / radiality** on both the structural and the
  operational (closed-switch) graph;
- a **graph/adjacency** representation for clients and the M2/M3 solvers.

This is the prerequisite for **P5-M2** (state estimation needs impedances + base
loads as pseudo-measurements) and **P5-M3** (three-phase power flow needs the full
electrical model).

## 2. What already existed (reused, not rebuilt)

| Asset | Source | Reused as-is |
|---|---|---|
| `grid_nodes` (8 types), `grid_edges` (line/switch/transformer/tie) | sql/013 | yes — extended with columns |
| Versioning (`network_model_versions`), customers, service_points | sql/013 | yes |
| Topology CRUD + `/graph` + `/downstream` | [topology.py](fastapi/routers/topology.py) | yes — extended |
| Backup feed TX-02 + normally-open tie E-TIE-01 | sql/015 | yes — used as the loop-detection example |
| DER registry (`der_assets`) | sql/016 | yes — M3 reads DER injection from it |
| Echo/telemetry read path | [device_state.py](fastapi/routers/device_state.py) | M2/M3 input |

The model already supported **feeders, substations, transformers, lines, switches,
tie switches, loads, DER nodes, batteries, solar plants, EV chargers** (via
`der_assets.der_type` + node binding). P5-M1 adds the **electrical layer** and
**reclosers**.

## 3. Schema changes — `sql/021_network_electrical.sql`

Idempotent, additive (`ADD COLUMN IF NOT EXISTS`, `UPDATE`), no table drops.

**`grid_nodes`** new columns:

| Column | Type | Meaning |
|---|---|---|
| `phases` | `VARCHAR(3)` NOT NULL default `'ABC'` | `ABC` / `A` / `AB` … connection |
| `base_load_kw` | `REAL` default 0 | nominal real load (pseudo-measurement source) |
| `base_load_kvar` | `REAL` default 0 | nominal reactive load |
| `load_class` | `VARCHAR(32)` | residential / ev / storage / generation / … |

Node-type CHECK widened to include **`recloser`**.

**`grid_edges`** new columns:

| Column | Type | Meaning |
|---|---|---|
| `resistance_r_ohm` | `REAL` | series R, **referred to the downstream node's base** |
| `reactance_x_ohm` | `REAL` | series X, same base |
| `length_km` | `REAL` | conductor length (documentation / future per-km models) |
| `ampacity_a` | `REAL` | thermal current limit (lines); transformers use `rating_kw` |
| `phases` | `VARCHAR(3)` NOT NULL default `'ABC'` | per-segment phasing |

### Impedance referencing convention

Impedance is stored in **ohms referred to the downstream node's voltage base**.
The P5-M3 solver converts to per-unit on each node's own `nominal_kv`, so an element
that spans two voltage levels (a distribution transformer, or the 33→11 kV head) is
handled automatically by the nodes' differing `nominal_kv` — no separate turns-ratio
column is required. This keeps the schema minimal and the solver general.

### Seeded Abuja Site A electrical model

11 nodes / 11 edges. Highlights:

- **Unbalance scenario (mission requirement):** the EV charger lateral `E-BUS-EV`
  and node `ND-EV001` are modeled **single-phase on A** (7.2 kW). Everything else is
  `ABC`. This makes the three-phase power flow (M3) produce genuinely unbalanced
  phase voltages.
- **Base load** lives on the metered residential node `ND-METER001` (80 kW / 25 kvar,
  3 customers) and the EV node; DER/storage nodes inject via telemetry (M2/M3).
- **Transformer impedance** (`E-TX-BUS`: R 0.002 Ω, X 0.0084 Ω ≈ 5 % on a 1 MVA LV
  base) and the parallel tie path (`E-TIE-01`) give M3 a meaningful voltage drop and
  M1 a meaningful loop.

## 4. API surface — additive endpoints on `/topology`

| Method · Path | Roles | Purpose |
|---|---|---|
| `GET /topology/validate` | read | Structural + electrical validation report (below) |
| `GET /topology/adjacency?closed_only=` | read | Adjacency map + connected components |
| CRUD `POST/PUT /topology/nodes` | engineer/admin | now accept `phases`, `base_load_kw`, `base_load_kvar`, `load_class` |
| CRUD `POST /topology/edges` | engineer/admin | now accept `resistance_r_ohm`, `reactance_x_ohm`, `length_km`, `ampacity_a`, `phases` |

All existing endpoints (`/graph`, `/downstream`, `/nodes`, `/edges`, `/version`,
`/edges/{id}/switch`, customers, service-points) are **unchanged**. New CRUD fields
are optional with safe defaults, so existing clients and tests are unaffected.

### `GET /topology/validate` response (seeded model)

```json
{
  "ok": true, "radial": true,
  "counts": {"nodes": 11, "edges": 11, "sources": 1, "components": 1},
  "structural_loops": 1, "operational_loops": 0,
  "loop_closing_switches": ["E-TIE-01"],
  "orphan_nodes": [], "multi_fed_nodes": [],
  "errors": [], "warnings": []
}
```

**Validation logic** (`validate_topology()`, pure + unit-callable):

- **Sources** — exactly-one substation expected; 0 → error, >1 → warning.
- **Orphans** — nodes in no structural component containing a source → error.
- **Loop detection** — cyclomatic number `|E| − |N| + components` on (a) the
  *structural* graph (all edges) and (b) the *operational* graph (closed edges).
  `operational_loops > 0` → error (radial operation requires a forest). A normally-
  open tie shows up as a **structural** loop (expected) and is listed under
  `loop_closing_switches`, not flagged as an error while open.
- **Parallel feed** — any node with ≥2 closed incoming edges → error (`multi_fed_nodes`).
- **Hierarchy consistency** — `parent_id` must exist and have a connecting edge;
  mismatches → warning.
- **Electrical completeness** — line/transformer/tie edges missing R/X → warning
  (so operators see which segments M2/M3 will treat as ideal).

## 5. Architecture

```
                 ┌─────────────────────────────────────────────┐
                 │            grid_nodes / grid_edges           │
                 │  connectivity (sql/013) + electrical (021)   │
                 └───────────────┬─────────────────────────────┘
                                 │ read
        ┌────────────────────────┼───────────────────────────────┐
        │                        │                                │
   topology.py              dms.py (legacy stub)         P5-M2 state_estimation
   /validate /adjacency      /state_estimation            (consumes R/X, base load)
   /graph /downstream             │                       P5-M3 powerflow
        │                         │                        (consumes full elec model)
   OMS / FLISR / DERMS ──────────┘
```

### Sequence — validation request

```
client ──GET /topology/validate──▶ topology.validate()
                                      ├─ _graph_rows()            (SELECT nodes, edges)
                                      ├─ build undirected + closed adjacency
                                      ├─ components(), cyclomatic loop count ×2
                                      ├─ orphan / source / parallel-feed checks
                                      ├─ parent↔edge hierarchy check
                                      └─ electrical completeness (SELECT)
                                   ◀── {ok, radial, loops, orphans, errors, warnings}
```

## 6. Validation results (isolated ephemeral DB)

Per the established protocol: throwaway `timescale/timescaledb:latest-pg16` on
`diep-lab_diep-net`, **all 22 migrations 000→021 applied cleanly** (021 idempotent,
no errors), then the live `validate_topology()` / graph logic executed from a
`python:3.12-slim` container against it. The shared platform DB was never touched.

| Check | Result |
|---|---|
| Migration 021 applies on full schema | ✅ `ok 021_network_electrical.sql` |
| Electrical columns populated for all 11 edges / 11 nodes | ✅ (R/X/ampacity/phases; base loads) |
| EV lateral single-phase | ✅ `E-BUS-EV.phases = 'A'`, `ND-EV001.phases = 'A'` |
| `recloser` node type accepted | ✅ insert/select/delete |
| Validate — seeded model | ✅ `ok=true, radial=true, structural_loops=1, operational_loops=0` |
| Tie identified as loop-closing switch | ✅ `loop_closing_switches=["E-TIE-01"]` |
| Close tie → operational loop detected | ✅ `ok=false, radial=false, operational_loops=1, multi_fed=["BUS-01"]` |
| Orphan node detected | ✅ injected `ORPH` → `orphan_nodes=["ORPH"], ok=false` |
| Adjacency / components | ✅ 1 component, 11 nodes |

Smoke tests: [`tests/test_p5_network_model.py`](tests/test_p5_network_model.py) (7
cases, integration-style against the live API, same harness as `test_topology_smoke`).

## 7. Rollback plan

- **Code:** revert the topology.py additions (new CRUD fields default-safe; new
  endpoints are purely additive — removing them affects no existing route).
- **Schema:** sql/021 only **adds** columns and one CHECK value. To fully revert
  (not required — additive columns are inert): `ALTER TABLE … DROP COLUMN IF EXISTS …`
  for the 9 columns and restore the prior CHECK. No data migration, no FK changes.
- **Risk of leaving it in place:** none — unused columns carry defaults; existing
  queries don't select them.

## 8. Risk assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Migration breaks existing schema | Low | additive only; validated on full 000→021 chain |
| New CRUD fields break existing clients | Low | optional with defaults; existing tests untouched |
| Validation endpoint load | Low | read-only, O(N+E) on an 11-node model; cacheable |
| Impedance values unrealistic → bad M2/M3 output | Med | seeded from typical LV/MV values; documented; per-feeder tunable; M3 validation cross-checks analytic drop |
| Loop logic false-positive on intended mesh | Low | structural vs operational separation; ties reported as informational while open |

## 9. Future extension points

- **Per-km line types** (conductor library → R/X from `length_km`) instead of
  absolute ohms.
- **Sequence impedances** (R0/X0) for unbalanced fault analysis.
- **Transformer detail**: tap position, vector group, on-load tap-changer state for
  Volt/VAR coordination.
- **Switching-plan validation**: given a proposed switch set, pre-check radiality
  before execution (reuse `validate_topology()` on a candidate edge state) — a
  natural guard for FLISR / OC-2.
- **Multi-substation / meshed** networks: the cyclomatic and component machinery
  already generalizes; M3's solver is the only radial-specific piece.

---

**Deliverables:** this design+validation doc · `sql/021_network_electrical.sql` ·
extended [topology.py](fastapi/routers/topology.py) · [tests/test_p5_network_model.py](tests/test_p5_network_model.py).
Next: **P5-M2 Distribution State Estimation** (WLS, consumes this electrical model).
