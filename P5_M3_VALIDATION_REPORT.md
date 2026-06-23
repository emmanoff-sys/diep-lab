# DIEP ADMS P5-M3 — Power Flow — Validation Report

**Module:** M3 — Three-phase Unbalanced Power Flow · **Branch:** `feature/adms-p5-advanced-dms`
**Method:** unit tests (pure engine) + isolated-DB end-to-end run. Shared platform DB untouched.

---

## 1. Unit tests — `tests/test_p5_powerflow.py`

Pure-Python, no services. Run in a `python:3.12-slim` container with pytest.

```
8 passed  (15 passed with M2 suite together)
```

| Test | Asserts |
|---|---|
| `test_balanced_load_matches_analytic_drop` | balanced 60 kW vs constant-power fixed point `V² − V + R_pu·P_pu = 0` (V ≈ 0.9638) within 0.002 |
| `test_unbalanced_load_produces_unbalance` | unbalanced load → phase a lowest, `unbalance_pct > 0.5` |
| `test_single_phase_lateral_only_has_its_phase` | `phases='A'` node solves with only phase a |
| `test_der_injection_raises_voltage` | negative load (DER export) raises that phase's voltage vs base case |
| `test_voltage_violation_detected` | high-impedance + heavy load → `voltage` violation recorded |
| `test_thermal_violation_detected` | tiny ampacity → `thermal` violation (>100%) recorded |
| `test_open_switch_de_energizes` | open switch → downstream `energized=false`, no phases |
| `test_converges_quickly` | converges in < 20 iterations |

**Per-unit bug caught & fixed during validation.** The thermal test initially failed
because the engine used a 1 MVA *per-phase* base instead of `S_3φ/3`, underestimating
currents/drops by 3×. Corrected to `SBASE_1PH_KW = SBASE_KW/3` and line-current base
`I_base = S_3φ/(√3·V_LL)`; the analytic balanced-drop test was re-derived to the
correct fixed point (0.9638) and now passes.

## 2. End-to-end — isolated ephemeral DB (Abuja Site A, 11 nodes)

Throwaway `timescale/timescaledb:latest-pg16`, all 22 migrations applied, fresh
telemetry seeded (METER001 load; BAT001/INV001/MG001 DER export), then the live
adapter (`dms._pf_loads`) + engine executed from a `python:3.12-slim` container.

**Solver summary**

```
method: three-phase backward/forward sweep (radial, per-phase series Z)
converged=True  iterations=5  max_mismatch=3.7e-07 pu  violations=0
```

**Node voltages (pu)** — note the genuine unbalance: phase a is consistently lower
because the **single-phase EV lateral (7.2 kW on phase a)** loads that phase only.

| Node | a | b | c | v_min | unbal % |
|---|---|---|---|---|---|
| SUB-ABUJA (slack) | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.00 |
| BUS-01 | 0.9724 | 0.9794 | 0.9794 | 0.9724 | 0.48 |
| ND-METER001 | 0.9510 | 0.9582 | 0.9582 | 0.9510 | 0.50 |
| ND-EV001 (1-φ) | 0.9659 | — | — | 0.9659 | n/a |

**Branch / transformer loading**

| Branch | S (kVA) | loading % | basis |
|---|---|---|---|
| E-SW-01 | 64.6 | 27.9 | ampacity |
| E-TX-BUS (xfmr) | 64.5 | 6.4 | rating_kva |
| E-BUS-METER | 81.9 | 59.9 | ampacity |
| E-BUS-EV (1-φ) | 7.2 | 49.4 | ampacity |

**Observations**

- Converged in 5 iterations to 3.7e-7 pu — fast, suitable for operational/interactive use.
- Slack held at exactly 1.0 pu balanced; voltages decrease monotonically toward the
  load (1.000 → 0.972 at the LV bus → 0.951 at the metered node, phase a).
- **Unbalance is physically correct**: the single-phase EV load depresses phase a by
  ~0.7 % relative to b/c at the shared upstream nodes — exactly the asymmetry M3
  exists to reveal and that a balanced (single-phase-equivalent) model would miss.
- DER export (battery/solar/microgrid as negative load) lifts local voltages and
  reduces upstream branch flow, visible in the modest LV-bus loadings.
- All nodes within the 0.95–1.05 band and all branches within rating → `violations=[]`
  on the healthy pilot operating point; the unit tests confirm violations are raised
  when limits are exceeded.

## 3. Result

**PASS.** The three-phase backward/forward sweep is correct against analytic cases,
converges quickly, produces a physically consistent **unbalanced** voltage/loading
profile on the pilot feeder, models single-phase laterals and DER injection, and
flags voltage/thermal violations — read-only, no new runtime dependencies, no impact
on existing functionality.
