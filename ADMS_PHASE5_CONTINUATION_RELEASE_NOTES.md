# DIEP ADMS Phase 5 (continuation) — Advanced DMS Applications — Release Notes

**Branch:** `feature/adms-p5-advanced-dms-cont` → (stacked on `feature/adms-p5-advanced-dms`)
**Scope:** the operational DMS applications built on the P5 foundation (M1 network
model, M2 state estimation, M3 power flow): **M4** optimal switching, **M5** N-1
contingency analysis, **M6** fault location.

**Safety posture:** **read-only**, like the rest of P5. No control plane, no Kafka,
no `OC_*` flags, no actuation — these produce *recommendations / analyses*; any live
switching would flow through the governed OC-2 / FLISR control plane. Additive,
backwards-compatible, **no new runtime dependencies** (pure-Python engines reusing
the M2/M3 `build_radial` + power flow). `.env` untouched.

---

## What shipped

| Module | Commit | Summary |
|---|---|---|
| **(M3 enh.)** loss output | `77de6f3` | `pf.solve` now returns `total_loss_kw` + per-branch `loss_kw` (Σ I²R). |
| **P5-M4** Optimal Switching | `77de6f3` | Minimum-loss feeder reconfiguration: exhaustive over reconfigurable switches, radial+fully-served feasibility, power-flow loss objective, tie-broken on fewest switch moves. `GET /dms/reconfiguration/recommend`. |
| **P5-M5** N-1 Contingency | `d12226a` | Per-element outage → greedy radial tie-restoration → post-contingency power flow → classify (secure/restorable/partial/unserved/violation) + rank. `GET /dms/contingency/n1`. |
| **P5-M6** Fault Location | `7a3af49` | Impedance (per-unit reactance-to-fault) + topological (last-gasp) + combined estimate. `POST /dms/fault_location/locate`. |

## New API (all additive, read roles)

```
GET  /dms/reconfiguration/recommend   min-loss switching plan vs current
GET  /dms/contingency/n1              N-1 over every element; ranked, n1_secure flag
POST /dms/fault_location/locate       {fault_current_a?, outage_nodes?} → ranked sections
```

## Architecture

```
M1 model + telemetry ─▶ dms.* adapters ─▶ pure engines (fastapi/dms/)
                                            reconfiguration.py ─┐
                                            contingency.py      ├─ reuse build_radial + powerflow.solve
                                            fault_location.py  ─┘
        all read-only endpoints on /dms ─▶ operators / planning / OMS / FLISR
```

Each engine is framework/DB-free and unit-tested standalone; the DB adapters live in
`routers/dms.py`. M4 evaluates configs with M3 power flow; M5 runs M3 per contingency
after FLISR-style restoration; M6 reuses the M2/M3 radial tree + pu impedances.

## Validation (shared platform DB never touched)

- **Pure unit tests: 28/28** across the P5 suite (M2 7 · M3 8 · **M4 4 · M5 4 · M6 5**),
  run in a clean `python:3.12-slim` container.
- **Isolated-DB end-to-end (Abuja Site A, all 22 migrations apply):**
  - **M4:** current config found already optimal (loss 3.16 kW; 8 evaluated / 4 feasible);
    a synthetic two-path feeder correctly reroutes off a high-R sectionalizer onto a
    low-R tie.
  - **M5:** `n1_secure=false`; TX-01-path failures (`E-SW-01`, `E-TX-BUS`) **restorable
    via the TX-02 tie `E-TIE-01`**; meter/source losses unserved; DER-branch losses
    flagged as voltage `violation`s.
  - **M6:** topological exact (meter→`E-BUS-METER`, LV bus→`E-TX-BUS`); combined
    2330 A + meter-dark → `E-BUS-METER` at **0.1 % impedance error**.
- **Bug caught by validation (M6):** raw-ohm impedance summation across voltage levels
  was non-physical (64 % error on the multi-level pilot) — switched to **per-unit**
  cumulative impedance; now monotonic and correct, 0.1 % on the in-range case.

## Deployment / rollback

- No schema changes (M4–M6 are pure compute on the existing M1 model + telemetry).
- The `fastapi/dms/` package gains `reconfiguration.py`, `contingency.py`,
  `fault_location.py` (+ the `pf.solve` loss fields) — rebuild/restart `diep-fastapi`
  to serve the new endpoints; running app unaffected until then.
- Rollback = remove the three endpoints + engine modules (and the additive loss
  fields). Nothing existing is touched.

## Limitations / next

Radial-only, planning-grade (LinDistFlow / per-phase scalar Z inherited from M2/M3);
M4 exhaustive search (heuristic hooks for large networks); M6 impedance is indicative
on short/stiff feeders (topology authoritative). Natural next steps: hand off M4/M5
results to governed OC-2/FLISR switching plans; multi-contingency (N-1-1); sequence-
impedance fault models; a portal Advanced-DMS panel.

Design + validation detail per module:
[P5_M4](P5_M4_RECONFIGURATION.md) · [P5_M5](P5_M5_CONTINGENCY.md) · [P5_M6](P5_M6_FAULT_LOCATION.md).
Commits preserved un-squashed (M4 → M5 → M6).
