# DIEP ADMS P5-M2 — Distribution State Estimation — Design

**Phase:** 23 (P5) · **Module:** M2 — Distribution State Estimation (WLS)
**Branch:** `feature/adms-p5-advanced-dms` · **Status:** implemented + validated
**Classification:** additive, read-only. No control plane, no flags, no new runtime deps.

---

## 1. Objective

Estimate the **complete electrical state** of the distribution feeder — voltage,
injection, branch flow and loading at *every* node — from **imperfect, sparse
telemetry**, replacing the M3 `dms.py` heuristic stub with a real **Weighted Least
Squares (WLS)** estimator. Requirements met: WLS approach, missing-data handling
(pseudo-measurements), **bad-data detection**, and per-node **confidence scoring**.

## 2. Why a *linear* WLS (and why no numpy)

The FastAPI image ships no numpy/scipy (reproducible-build constraint). The feeder
is small and **radial**, which lets us use the **LinDistFlow** linearization, under
which voltage is a *linear* function of nodal injections — so the estimate is the
**closed-form normal-equations solution**, no Gauss-Newton iteration, solved with a
tiny pure-Python Gaussian-elimination helper ([fastapi/dms/linalg.py](fastapi/dms/linalg.py)).
This is fast (sub-millisecond on tens of nodes), dependency-free, and numerically
well-behaved on a model this size.

## 3. Mathematical model

**State** `x = [pₖ, qₖ]` — net real/reactive injection at every energized non-source
node (load positive, generation negative).

**Radial structure.** On a tree rooted at the substation, branch *b* carries the sum
of its subtree's injections:  `P_b = Σ_{k∈subtree(b)} pₖ`,  `Q_b = Σ … qₖ`.

**Voltage (LinDistFlow, per-unit).**

```
V_n = 1 − Σ_{b ∈ path(root→n)} [ R_pu(b)·P_b/Sbase + X_pu(b)·Q_b/Sbase ]
```

with `R_pu = R_ohm / Zbase`, `Zbase = V_base_kv² / S_base_MVA`, `S_base = 1 MVA`.
Both injection measurements (`zₖ = pₖ`) and voltage measurements (`z = 1 − V_n`,
linear in x via the path/subtree coefficients) are linear, giving

```
x̂ = (Hᵀ W H)⁻¹ Hᵀ W z ,   W = diag(1/σ²)
```

**Measurements & weights**

| Type | Source | σ (default) | Role |
|---|---|---|---|
| Real injection | telemetry `grid_import_kw`/`power_kw` | 2 kW | trusted |
| Reactive injection | telemetry (if present) | 2 kvar | trusted |
| Voltage magnitude (pu) | telemetry `voltage` ÷ phase base | 0.004 pu | trusted |
| **Pseudo** real/reactive | node `base_load_kw/kvar` (M1) | 30 kW / 20 kvar | observability filler |

Pseudo-measurements anchor **every** state variable, so the system stays observable
where telemetry is missing — they carry large σ (small weight), so a real
measurement at the same node dominates. This is the **missing-data handling**
mechanism.

## 4. Diagnostics

- **Bad-data detection** — largest-normalized-residual test: `rₙ,i = |rᵢ| / √Ωᵢᵢ`,
  `Ω = R − H G⁻¹ Hᵀ` (residual covariance). If `max rₙ > 3.0`, the offending
  measurement (type + node) is reported.
- **χ² consistency** — objective `J(x̂) = rᵀ W r` compared to the 99% critical value
  at `dof = m − n`; `chi2_ok=false` signals systematic measurement/model error.
- **Confidence per node** — from the estimated-voltage variance `hₙ G⁻¹ hₙᵀ`:
  `confidence = clip(1 − σ_V / 0.04pu, 0, 1)`, with a floor of 0.85 for directly
  measured nodes. High redundancy / nearby meters ⇒ high confidence; pseudo-only
  pockets ⇒ low.

## 5. Outputs

Per **node**: `estimated_voltage_pu`, `estimated_voltage_kv`, `estimated_p_kw`,
`estimated_q_kvar`, `energized`, `monitored`, `confidence`.
Per **branch**: `p_kw`, `q_kvar`, `s_kva`, `current_a`, `loading_pct` (vs ampacity,
or vs `rating_kw` for transformers).
Top level: `measurements`, `states`, `redundancy`, `objective_J`, `dof`, `chi2_ok`,
`bad_data`, `max_normalized_residual`.

## 6. Architecture & integration

```
telemetry (TimescaleDB) ─┐
grid_nodes/edges (M1) ───┼─▶ dms._se_{nodes,edges,measurements}()  [adapter, DB]
der_assets ──────────────┘            │
                                       ▼
                       dms.state_estimation.estimate()  [pure engine]
                          build_radial → assemble z,H,W → solve → diagnostics
                                       │
                       GET /dms/se/estimate  (read roles)  ──▶ operators / M3 / portal
```

- **Pure engine** [fastapi/dms/state_estimation.py](fastapi/dms/state_estimation.py)
  — no DB/framework, unit-tested standalone.
- **Adapter + endpoint** in [fastapi/routers/dms.py](fastapi/routers/dms.py)
  (`GET /dms/se/estimate`). The legacy `/dms/state_estimation` stub is **retained**
  for backwards compatibility.
- Read-only; no Kafka, no actuation, neither operational flag involved.

### Sequence

```
client ─GET /dms/se/estimate─▶ dms.se_estimate()
   ├─ _se_nodes()/_se_edges()           (SELECT M1 electrical model)
   ├─ _se_measurements()                (latest fresh telemetry → z, pu voltages)
   ├─ state_estimation.estimate()       (WLS solve + bad-data + confidence)
   └─◀ {nodes[], branches[], J, chi2_ok, bad_data, redundancy}
```

## 7. Rollback

Remove the `/dms/se/estimate` endpoint + adapter from `dms.py` and delete the
`fastapi/dms/` package. Purely additive — no schema, no existing route touched.

## 8. Risk assessment

| Risk | Severity | Mitigation |
|---|---|---|
| LinDistFlow inaccuracy on heavily loaded / long lines | Med | acceptable for situational awareness; M3 (full power flow) is the high-fidelity cross-check; documented |
| Pseudo-measurements bias estimate where telemetry sparse | Med | large σ; confidence score exposes low-trust nodes; flagged `monitored=false` |
| Bad telemetry corrupts estimate | Low | normalized-residual detection flags it; χ² guard |
| Singular gain matrix (unobservable) | Low | pseudo-measurements guarantee full rank; `solve()` raises → 409 |

## 9. Future extension points

- Full non-linear AC WLS (Gauss-Newton) for meshed networks (reuse `linalg`).
- Three-phase DSSE keyed off M1 `phases` (M3 already three-phase).
- Automatic bad-data **removal + re-estimation** loop (currently report-only).
- Historical-measurement smoothing / forecasting pseudo-measurements (tie to
  `forecasting.py`).

See [P5_M2_VALIDATION_REPORT.md](P5_M2_VALIDATION_REPORT.md) for results.
Deliverables: engine + linalg, `GET /dms/se/estimate`,
[tests/test_p5_state_estimation.py](tests/test_p5_state_estimation.py) (7 unit cases).
