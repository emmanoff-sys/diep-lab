# DIEP ADMS P5-M4 — Optimal Network Reconfiguration — Design & Validation

**Phase:** 23 (P5 continuation) · **Module:** M4 — Optimal Switching
**Branch:** `feature/adms-p5-advanced-dms-cont` · **Status:** implemented + validated
**Classification:** additive, **read-only** (recommendation only — no actuation, no flags).

---

## 1. Objective

Recommend the switch configuration that **minimizes feeder losses** while keeping the
network **radial**, **fully served** (no load shed), and within **voltage/thermal
limits** — the classic distribution feeder reconfiguration problem. Output is a
*switching plan*; live execution would flow through the governed OC-2 switch / FLISR
control plane (not part of this read-only module).

## 2. Method

- **Search:** exhaustive over the *reconfigurable* switches — switchable
  sectionalizers (`switch`) and ties (`tie`), excluding device-islanding breakers
  (`attrs.role='islanding_breaker'`, which island a DER rather than reroute load).
  Exact for the handful of switches on a feeder section (2ⁿ, n small); the same
  per-config evaluator plugs into a branch-exchange heuristic for large networks
  (extension point).
- **Feasibility per config** (`_radial_feasible`): over the closed edges, the network
  energized from the substation must be a **tree** (radiality: closed intra-energized
  edges = |energized| − #sources) **and** every `load`/`meter` node energized.
- **Objective:** total **I²R loss** from the M3 power flow (`total_loss_kw`, added to
  `pf.solve` in this module). Min loss wins; **tie-break on fewest switching changes**
  from the current state so an equal-loss config never proposes a pointless move.
- Reports current vs recommended (loss, violations, max loading), the switching plan
  (diff), and loss reduction (kW + %).

## 3. M3 enhancement — loss output

`pf.solve` now returns `total_loss_kw` and per-branch `loss_kw` (`Σ_phase I²R`,
physical amps × per-phase ohms). Generally useful; M4's objective.

## 4. Architecture & integration

```
_se_nodes/_se_edges (M1, incl. is_switchable + attrs) ─┐
_pf_loads (telemetry/base) ────────────────────────────┼─▶ reconfiguration.recommend()
                                                         │     ├─ enumerate switch combos
                                                         │     ├─ _radial_feasible() filter
                                                         │     └─ pf.solve() → min-loss pick
                              GET /dms/reconfiguration/recommend (read) ─▶ operators
```

Pure engine [fastapi/dms/reconfiguration.py](fastapi/dms/reconfiguration.py); adapter +
endpoint in [routers/dms.py](fastapi/routers/dms.py). Read-only; no Kafka/actuation/flags.

## 5. Validation

**Unit tests** [tests/test_p5_reconfiguration.py](tests/test_p5_reconfiguration.py) — 4/4:
two-path feeder where rerouting load off a high-impedance sectionalizer onto a
low-impedance tie cuts loss → engine recommends `open EA` + `close EB`, loss reduction
> 0; feasible configs keep load served (no shed); already-optimal config proposes
nothing; islanding breakers excluded from the search.

**Isolated-DB end-to-end (Abuja Site A):** 8 configs evaluated, **4 feasible**; the
current config (tie open, both sectionalizers closed) is found **already optimal**
(loss 3.158 kW, no violations, max loading 59.9 %) → `action_required=false`. Correct:
the radial pilot feeder has no lower-loss reroute (the TX-02 tie path is not cheaper).

## 6. Rollback / risk / extensions

- **Rollback:** remove the endpoint + `fastapi/dms/reconfiguration.py`; revert the
  `pf.solve` loss additions (additive). No schema, no existing route touched.
- **Risk:** read-only recommendation; low. Exhaustive search bounded by switch count.
- **Extensions:** branch-exchange / heuristic search for large networks; multi-objective
  (loss + load balancing + switching cost); contingency-aware reconfiguration (feed
  M5); one-click hand-off to a governed OC-2 switching plan.
