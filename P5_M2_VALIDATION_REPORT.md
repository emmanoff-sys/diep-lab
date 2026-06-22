# DIEP ADMS P5-M2 — State Estimation — Validation Report

**Module:** M2 — Distribution State Estimation (WLS) · **Branch:** `feature/adms-p5-advanced-dms`
**Method:** unit tests (pure engine) + isolated-DB end-to-end run. Shared platform DB untouched.

---

## 1. Unit tests — `tests/test_p5_state_estimation.py`

Pure-Python, no services. Run in a `python:3.12-slim` container with pytest.

```
7 passed in 0.11s
```

| Test | Asserts |
|---|---|
| `test_linalg_solve_and_inverse` | Gaussian solve + Gauss-Jordan inverse correct (A·A⁻¹ = I) |
| `test_recovers_injection_and_voltage_from_power_meter` | recovers 50 kW load and analytic drop V = 1 − R_pu·P_pu within 0.003 pu |
| `test_voltage_measurement_infers_load` | a **voltage-only** measurement infers the 50 kW load within 5 kW |
| `test_missing_telemetry_uses_pseudo_and_lowers_confidence` | unmonitored node falls back to base-load pseudo; confidence < monitored |
| `test_bad_data_detection_flags_inconsistent_voltage` | conflicting P vs V → `bad_data` flagged, max normalized residual > 3 |
| `test_open_switch_de_energizes_subtree` | open switch → downstream `energized=false`, no estimate |
| `test_branch_flow_and_loading_reported` | branch P, current (A) and loading % reported |

**Analytic cross-check.** 2-node feeder, R = 0.1 Ω on a 0.415 kV base
(Zbase = 0.172 Ω → R_pu = 0.5806), P = 50 kW (0.05 pu): predicted drop
0.5806 × 0.05 = **0.0290 pu**, V = 0.9710. Estimator output matched within 0.003 pu.

## 2. End-to-end — isolated ephemeral DB (Abuja Site A, 11 nodes)

Throwaway `timescale/timescaledb:latest-pg16`, all 22 migrations applied, fresh
telemetry seeded for METER001 / BAT001 / INV001 / MG001, then the live adapter
(`dms._se_*`) + engine executed from a `python:3.12-slim` container.

**Solver summary**

```
method: WLS (LinDistFlow injection-state, normal equations)
measurements=28  states=20  redundancy=1.40  J=9.841  dof=8  chi2_ok=True
max_normalized_residual=2.79  bad_data=None
```

`J = 9.84 < χ²₀.₉₉(8) = 20.09` → measurements consistent; no bad data (max
normalized residual 2.79 < 3.0).

**Estimated state (selected)**

| Node | V (pu) | P (kW) | conf | monitored |
|---|---|---|---|---|
| SUB-ABUJA | 1.0000 | 0.00 | 1.00 | — |
| TX-01 | 0.9656 | — | 0.92 | — |
| BUS-01 | 0.9634 | — | 0.95 | — |
| ND-METER001 | 0.9448 | 77.51 | 0.94 | ✅ (telem 78 kW) |
| ND-EV001 | 0.9598 | 11.79 | 0.79 | — (pseudo) |
| ND-MG001 | 0.9629 | 5.10 | 0.95 | ✅ |

**Estimated branch flows / loading (selected)**

| Branch | P (kW) | I (A) | loading % |
|---|---|---|---|
| E-SW-01 | 108.1 | 153.3 | 38.3 |
| E-TX-BUS (xfmr) | 103.7 | 147.1 | 10.6 |
| E-BUS-METER | 77.5 | 108.2 | 54.1 |
| E-BUS-EV | 11.8 | 16.5 | 26.2 |

**Observations**

- Voltage profile is physically sound: 1.000 pu at the source decreasing
  monotonically to 0.945 pu at the most heavily loaded (metered) node.
- The metered injection (77.5 kW) matches the 78 kW telemetry input — the trusted
  measurement dominates its weak pseudo-measurement, as designed.
- Unmonitored nodes (EV) carry visibly lower confidence (0.79) than measured nodes
  (≥0.92), correctly surfacing where the estimate leans on pseudo-measurements.
- Branch loadings are within ratings; `E-BUS-METER` at 54% is the most loaded LV
  segment — the kind of insight M2 exists to provide.

## 3. Result

**PASS.** WLS estimator is correct against analytic cases, observable under missing
data via pseudo-measurements, detects bad data, scores confidence, and produces a
physically consistent full-feeder state on the pilot network — read-only, no new
runtime dependencies, no impact on existing functionality.
