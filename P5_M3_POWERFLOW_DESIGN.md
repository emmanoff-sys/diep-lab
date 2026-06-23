# DIEP ADMS P5-M3 — Unbalanced Power Flow — Design

**Phase:** 23 (P5) · **Module:** M3 — Three-phase Power Flow
**Branch:** `feature/adms-p5-advanced-dms` · **Status:** implemented + validated
**Classification:** additive, read-only. No control plane, no flags, no new runtime deps.

---

## 1. Objective

Compute the **unbalanced three-phase** operating point of a radial distribution
feeder — per-phase voltage, current, branch/transformer loading, and constraint
violations — from the M1 electrical model plus loads/DER injection. This is the
high-fidelity complement to M2: where state estimation infers state from sparse
telemetry, power flow *computes* state from an assumed load/generation pattern
(planning, what-if switching, DER hosting, FLISR feasibility).

Requirements met: single- and three-phase loads, DER injection, battery dispatch
effect, transformer loading, voltage-drop; outputs voltage/current profiles,
feeder loading, transformer utilization, constraint violations; radial assumption
with a modular path to meshed; fast enough for operational use.

## 2. Method — backward/forward sweep (ladder iterative)

Radial feeders converge reliably with the **current-summation backward/forward
sweep** (Kersting), avoiding any admittance-matrix factorization:

```
init    : flat start — every node phase at the slack profile 1∠0 / 1∠−120 / 1∠+120 pu
repeat  :
  backward : iₙᵠ = conj(Sₙᵠ / Vₙᵠ)              (constant-power load currents)
             Jbᵠ = Σ_{k∈subtree(b)} iₖᵠ           (branch currents, leaves → root)
  forward  : V_childᵠ = V_parentᵠ − Zbᵠ · Jbᵠ     (root → leaves)
until    max |ΔV| < tol  (default 1e-6 pu, ≤100 iters)
```

Reuses the radial tree (`build_radial`) from M2 — root, per-node path edges,
per-edge subtree, per-edge **pu** impedance — so M2 and M3 share one topology
engine.

### Per-unit system (the subtle part)

Three-phase base `S_3φ = 1 MVA`; per-node voltage base = `nominal_kv` (line-line);
`Zbase = V_LL² / S_3φ`. Crucially the **per-phase power base is `S_3φ/3`**, so the
per-phase pu current `conj(S_1φ/V)` equals the line current in pu and the per-phase
drop reproduces the three-phase single-line result. (A 1 MVA *per-phase* base — the
bug caught in validation — underestimates drops/currents by 3×.) Line current base
`I_base = S_3φ/(√3·V_LL)`; per-phase apparent power uses the `S_3φ/3` base, summed
over phases to a three-phase kVA for transformer-rating comparison.

### Voltage-level crossings

Impedance is referred to the downstream base (M1 convention), and every node sits
near 1 pu on its own `nominal_kv`. A transformer (or the 33→11 kV head) is therefore
handled automatically by the differing bases — no explicit turns ratio. Delta-wye
phase shift and Carson mutual coupling (off-diagonal `Zabc`) are **documented future
extensions**; the per-phase scalar-Z model already yields true unbalance from
per-phase loads and single-phase laterals.

## 3. Unbalance & DER modeling

- **Single-phase laterals**: M1 `phases='A'` ⇒ the node/branch carries only phase a;
  its load shifts that phase down relative to b/c (real unbalance).
- **Per-phase loads**: balanced loads split evenly; explicitly unbalanced loads are
  supported by the per-phase `loads[node][phase]` input.
- **DER / battery**: telemetry power on a `der` node enters as **negative load**
  (export raises local voltage) — so battery dispatch and solar export are visible
  in the voltage/loading result.

## 4. Outputs

Per **node**: `phases.{a,b,c}.{v_pu, v_volts, angle_deg}`, `v_min_pu`, `v_avg_pu`,
`unbalance_pct` (max phase deviation from average, three-phase nodes).
Per **branch**: `phases.{p}.{current_a, s_kva}`, total `s_kva`, `loading_pct` with
`loading_basis` (`ampacity` for lines, `rating_kva` for transformers).
Top level: `converged`, `iterations`, `max_mismatch_pu`, `v_band_pu`, and a
`violations` list (`voltage` outside band, `thermal` over 100%).

## 5. Architecture & integration

```
grid_nodes/edges (M1 electrical) ─┐
telemetry (DER injection) ────────┼─▶ dms._pf_loads()  [adapter, DB]
node base loads (M1) ─────────────┘            │
                                                ▼
                       dms.powerflow.solve()  [pure engine: build_radial → sweep]
                                                │
                       GET /dms/powerflow/solve (read roles) ─▶ operators / planning / FLISR
```

- **Pure engine** [fastapi/dms/powerflow.py](fastapi/dms/powerflow.py) — `complex`
  + the M2 tree builder; no numpy, no DB. Unit-tested standalone.
- **Adapter + endpoint** in [fastapi/routers/dms.py](fastapi/routers/dms.py)
  (`GET /dms/powerflow/solve`). Read-only; no Kafka, no actuation, no flags.
- **Modularity for meshing**: the sweep driver is separate from the per-branch
  impedance model; a meshed solver (Newton / Z-bus) can replace the driver while
  keeping the topology adapter and result schema.

### Sequence

```
client ─GET /dms/powerflow/solve─▶ dms.powerflow_solve()
   ├─ _se_nodes()/_se_edges()       (M1 electrical model incl. per-edge phases)
   ├─ _pf_loads()                   (telemetry/base → per-phase complex loads)
   ├─ powerflow.solve()             (backward/forward sweep to tolerance)
   └─◀ {converged, nodes[phases], branches[loading], violations}
```

## 6. Rollback

Remove `/dms/powerflow/solve` + `_pf_loads` from `dms.py` and delete
`fastapi/dms/powerflow.py`. Purely additive — no schema, no existing route touched.

## 7. Risk assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Non-convergence on pathological data | Low | radial sweep is robust; capped iters + `converged` flag exposed; 5 iters on pilot |
| Per-phase scalar Z ignores mutual coupling | Med (accuracy) | acceptable for planning-grade unbalance; documented; architecture supports 3×3 Zabc |
| Transformer phase shift omitted | Low | magnitudes unaffected; flagged as future work |
| Bad load input → misleading result | Low | read-only output; operator-facing; no actuation |

## 8. Future extension points

- Carson 3×3 series + shunt impedance (full mutual coupling).
- Delta-wye transformer models with phase shift; OLTC tap in the sweep.
- Meshed/weakly-meshed solver (loop-breaking compensation or Newton) behind the
  same adapter.
- Voltage-dependent (ZIP) load models; unbalanced fault analysis via M1 R0/X0.
- Feed M3 violations into Volt/VAR (OC-4) and FLISR feasibility checks.

See [P5_M3_VALIDATION_REPORT.md](P5_M3_VALIDATION_REPORT.md) for results.
Deliverables: engine, `GET /dms/powerflow/solve`,
[tests/test_p5_powerflow.py](tests/test_p5_powerflow.py) (8 unit cases).
