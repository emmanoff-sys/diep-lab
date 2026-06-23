# DIEP ADMS Phase 5 — Advanced DMS Foundation — Release Notes

**Branch:** `feature/adms-p5-advanced-dms` → `main`
**Scope:** turn DIEP from a *connectivity-aware* ADMS into a *network-intelligent*
one — the analytical foundation for FLISR, Volt/VAR, contingency and outage work to
come. Three modules: **M1** electrical network model, **M2** distribution state
estimation (WLS), **M3** unbalanced three-phase power flow.

**Safety posture:** this entire phase is **read-only**. No control plane, no Kafka,
no actuation, **no operational flags** (`OC_CONTROLS_ENABLED` / `OC_AUTOMATION_ENABLED`
are irrelevant here) — the lowest-risk tier of the whole ADMS arc. All changes are
**additive and backwards-compatible**: one idempotent SQL migration, additive
read endpoints on existing routers, and a new pure-Python analytics package. `.env`
untouched. **No new runtime dependencies** — the engines use a tiny pure-Python
linear-algebra/`complex` core so the FastAPI image stays numpy/scipy-free and its
builds reproducible.

---

## What shipped

| Module | Commit | Summary |
|---|---|---|
| **P5-M1** Network Model Service | `c30cca0` | `sql/021` adds electrical attributes (R/X, length, ampacity, phases; node base load + phasing; `recloser` type) to the M1 model + Abuja seed (EV lateral single-phase for real unbalance). `GET /topology/validate` (orphan/source/parallel-feed, parent-edge hierarchy, **loop detection + radiality** via cyclomatic number on structural vs operational graph) and `GET /topology/adjacency`. |
| **P5-M2** State Estimation (WLS) | `01f28fc` | `fastapi/dms/{linalg,state_estimation}.py`: weighted-least-squares DSSE on the LinDistFlow model; pseudo-measurements for missing data; largest-normalized-residual **bad-data detection** + χ² check; per-node **confidence**. `GET /dms/se/estimate`. |
| **P5-M3** Power Flow (3-phase) | `4b309fd` | `fastapi/dms/powerflow.py`: three-phase **backward/forward sweep** for radial feeders; single-phase laterals + DER injection ⇒ true unbalance; per-phase V/I, transformer utilization, voltage/thermal **violations**. `GET /dms/powerflow/solve`. |

The legacy `GET /dms/state_estimation` heuristic stub is **retained** for backwards
compatibility; new clients use the M2/M3 endpoints.

## New / changed API (all additive, read roles)

```
GET /topology/validate            structural+electrical validation, loop/radiality
GET /topology/adjacency           adjacency map + connected components
GET /dms/se/estimate              WLS state estimate (nodes V/P/conf, branch flow/loading)
GET /dms/powerflow/solve          3-phase power flow (per-phase V, loading, violations)
POST/PUT /topology/nodes,/edges   now accept the new electrical fields (optional, defaulted)
```

## Architecture

```
                         grid_nodes / grid_edges  (M1 connectivity + electrical)
                                     │  read-only
        ┌────────────────────────────┼─────────────────────────────────────┐
        │                            │                                      │
  topology.py                   routers/dms.py  ──▶  fastapi/dms/ (pure engines)
  /validate /adjacency          adapters + endpoints      linalg.py
        │                            │                     state_estimation.py (M2 WLS)
  OMS / FLISR / DERMS              telemetry               powerflow.py        (M3 sweep)
  (unchanged consumers)         (TimescaleDB)              └ shared build_radial tree
```

Engines are framework/DB-free pure functions (unit-tested standalone); the DB
adapters live in the routers. M2 and M3 share one radial-topology builder.

## Validation (shared platform DB never touched)

Per the established protocol: throwaway `timescale/timescaledb:latest-pg16` on
`diep-lab_diep-net` with **all 22 migrations 000→021 applied**, plus pure unit tests
in a `python:3.12-slim` container.

- **Unit tests:** M2 `test_p5_state_estimation` (7) + M3 `test_p5_powerflow` (8) =
  **15/15**, incl. analytic cross-checks (LinDistFlow drop; constant-power fixed
  point), bad-data detection, missing-data/pseudo, unbalance, DER lift, violations.
- **M1 isolated-DB:** validate detects the normally-open tie as a structural loop,
  flags an operational loop + parallel feed when the tie is closed, and detects
  injected orphans; `recloser` type accepted.
- **M2 isolated-DB (Abuja):** 28 measurements / 20 states, redundancy 1.40,
  J = 9.84 < χ²₀.₉₉(8), no bad data; physical 1.0→0.945 pu profile; metered injection
  recovered (77.5 vs 78 kW); confidence lower on unmonitored nodes.
- **M3 isolated-DB (Abuja):** converges in 5 iters to 3.7e-7 pu; true unbalance from
  the single-phase EV lateral (phase a depressed ~0.7 %); branch loadings within
  rating; violations empty on the healthy operating point.
- **Bug caught by validation:** an M3 per-unit base error (1 MVA/phase vs `S_3φ/3`,
  3× current/drop underestimate) was caught by the thermal-violation unit test and
  fixed before commit.

## Deployment / migration

- Apply `sql/021_network_electrical.sql` (idempotent; additive columns + the
  `recloser` type; wire into `init-db.sh` alongside 000–020).
- **The new `fastapi/dms/` package must be present in the API image** (it is imported
  by `routers/dms.py`). Rebuild/restart `diep-fastapi` to pick up M2/M3; until then
  the running app is unaffected (old code).
- No change to existing services, no flags, no env. Rollback = drop the additive
  columns (optional — they are inert) and remove the additive endpoints/package.

## Risk & limitations (carried for the next phase)

- M2 uses the **LinDistFlow linearization**; M3 uses **per-phase scalar impedance**
  (no Carson mutual coupling) and omits transformer phase shift — all planning-grade
  and documented, with the modular hooks to upgrade to full `Zabc` / Newton / meshed
  solvers. See the per-module design docs for the extension points.
- Both are **radial-only** today (mission scope); the topology validation already
  flags non-radial operation, and the solver architecture is meshed-ready.

Design + validation detail:
[P5_M1](P5_M1_NETWORK_MODEL_DESIGN.md) ·
[P5_M2 design](P5_M2_STATE_ESTIMATION_DESIGN.md) / [report](P5_M2_VALIDATION_REPORT.md) ·
[P5_M3 design](P5_M3_POWERFLOW_DESIGN.md) / [report](P5_M3_VALIDATION_REPORT.md).
Commits are preserved **un-squashed and un-rebased** (M1 → M2 → M3).
