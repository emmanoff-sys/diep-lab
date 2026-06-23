# DIEP ADMS P5-M6 — Fault Location — Design & Validation

**Phase:** 23 (P5 continuation) · **Module:** M6 — Fault Location
**Branch:** `feature/adms-p5-advanced-dms-cont` · **Status:** implemented + validated
**Classification:** additive, **read-only**. No actuation, no flags.

---

## 1. Objective

Estimate **where** a fault is on a radial feeder, from whatever evidence is
available, by two complementary methods that reinforce each other:

- **Impedance (reactance-to-fault):** from a measured fault-current magnitude at the
  substation, find the section whose cumulative impedance from the source produces
  that current.
- **Topological (last-gasp):** from the set of meters/nodes reporting loss of power,
  find the edge whose downstream subtree matches the dark set.

## 2. Method

**Impedance.** For a bolted three-phase fault, `I = V / |Z_path|`. Crucially the
cumulative impedance is summed in **per-unit** (from `build_radial`), not raw ohms —
the pilot spans 33→11→0.415 kV and adding ohms across levels is meaningless, whereas
pu impedance is on a consistent base. `I_pu = 1/|Z_pu|`, converted to amps at the
faulted node's base (`I_base = S_base/(√3·V_LL)`). Each non-source node is a candidate
("fault just past its feeding section"), ranked by current-match error. Radial
branching yields several near-equidistant candidates — all returned, ranked.

**Topological.** For each section, the downstream subtree is compared to the reported
dark set by Jaccard overlap; the best-matching section (ideally an exact match) is the
fault location. Robust to partial reports.

**Combined.** When both inputs exist, topology selects the faulted lateral and the
impedance candidate within that lateral gives the distance — the `best_estimate`.

## 3. Architecture & integration

```
_se_nodes/_se_edges (M1, impedances + lengths) ─▶ fault_location.locate()
        fault_current_a ─┐                          ├─ impedance pu ranking
        outage_nodes ────┘                          ├─ topological subtree match
                                                     └─ combined best_estimate
            POST /dms/fault_location/locate (read) ─▶ operators / OMS / FLISR
```

Pure engine [fastapi/dms/fault_location.py](fastapi/dms/fault_location.py); endpoint
(POST, body = `fault_current_a` and/or `outage_nodes`) in
[routers/dms.py](fastapi/routers/dms.py). Read-only; no Kafka/actuation/flags.

## 4. Validation

**Unit tests** [tests/test_p5_fault_location.py](tests/test_p5_fault_location.py) — 5/5
on a single-level linear feeder with known cumulative impedance: impedance method
locates the correct section (<1% error), nearer/farther faults rank by current,
topological method finds the section from outage reports, combined estimate fuses
both, and impedance-only works when no outage report is given.

**Isolated-DB end-to-end (Abuja Site A):**
- **Topological** (the workhorse on this compact feeder): meter dark → `E-BUS-METER`
  (exact match); whole LV bus dark → `E-TX-BUS` (Jaccard 1.0).
- **Impedance**: pu-correct and monotonic across the 33/11/0.415 kV levels. On this
  electrically *stiff* pilot all LV sections sit at high fault current (~2.1–3.4 kA),
  so an in-range measurement resolves cleanly — e.g. **2330 A + meter-dark report →
  `E-BUS-METER`, impedance error 0.1 %, topology-confirmed** (`best_estimate`
  method `topological+impedance`).

**Limitation (documented):** on a short/stiff feeder, sections are electrically close,
so impedance alone is *indicative* and topology is authoritative; on a longer
single-voltage feeder (unit-test case) impedance alone is precise. The two together
are the robust answer.

## 5. Rollback / risk / extensions

- **Rollback:** remove the endpoint + `fastapi/dms/fault_location.py`. Additive.
- **Risk:** read-only estimate; low. No dependence on protection telemetry beyond the
  optional inputs.
- **Extensions:** reactance-only (X/R) distance for better accuracy under fault
  resistance; per-phase / sequence-impedance fault models (LG/LL/LLG) using M1 R0/X0;
  fuse/recloser trip-state input; auto-handoff of the located section to a governed
  FLISR isolation plan (M5) and OMS incident.
