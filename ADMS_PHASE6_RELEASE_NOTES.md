# DIEP ADMS Phase 6 — OMS / AMI Depth — Release Notes

**Branch:** `feature/adms-p6-oms-ami` → `main`
**Scope:** deepen outage management with AMI-driven inference and decision support:
**M7** outage detection/inference, **M8** inference-vs-N-1 validation hooks, **M9**
crew-dispatch recommendation.

**Safety posture:** **read-only**, like P5. No control plane, no Kafka, no `OC_*`
flags, no actuation, no ticketing/CAD integration — these produce *inferences and
recommendations* only. Additive, backwards-compatible, **no new runtime
dependencies** (pure-Python engines reusing the P5 `build_radial` + N-1 contingency).
`.env` untouched.

---

## What shipped

| Module | Commit | Summary |
|---|---|---|
| **P5-M5 enh.** | (M8) | N-1 now reports pre-restoration `lost_customers` per element. |
| **P6-M7** Outage Inference | `165d36f` | From AMI last-gasp signals + M1 topology + customer→transformer map: cluster dark meters by transformer, LCA of each cluster → **probable failed device**, estimate **all** downstream customers, confidence. `GET /oms/outage/infer`. |
| **P6-M8** Validation Hooks | `ce31d0d` | Cross-check M7 vs M5 N-1; **flag** customer-count mismatch / device-not-in-model (real disagreements) and informational flags (restorable-via-tie, n1-confirms-unserved). Does **not** auto-resolve. `GET /oms/outage/validate`. |
| **P6-M9** Crew Dispatch | `309e254` | Rank outage locations by customers affected + restoration complexity (tie availability from M5): field-repair (crew) before remote-switch. Advisory only. `GET /oms/crew/recommend`. |

## New API (all additive, read roles)

```
GET /oms/outage/infer       probable device(s) + affected customers from AMI last-gasp
GET /oms/outage/validate    M7 vs M5 N-1 cross-check, flagged mismatches
GET /oms/crew/recommend     prioritized crew-dispatch list (read-only)
```

These sit alongside the existing OMS (`/oms/detect`, `/cases`, `/outages`, `/kpis`),
reusing its `_meters_out` last-gasp signal path and the M1 network model.

## Design highlights

- **M7** sharpens the existing OMS (which groups dark meters at the nearest
  switchable section) into a *device-level* inference: dark meters are clustered by
  feeding transformer (customer→transformer mapping), and within each cluster the
  **deepest common ancestor** of the dark meter nodes is the smallest section whose
  loss explains every dark meter — its feeding edge is the **probable failed
  device**. Affected customers = **all** downstream (AMI coverage is partial, so the
  reported set is a lower bound). Confidence = fraction of the section's meters that
  went dark.
- **M8** treats M7 (from live AMI) and M5 (what-if N-1) as independent estimators and
  surfaces where they disagree — a model/telemetry-gap detector, deliberately
  *flag-only* (no silent reconciliation).
- **M9** turns restorability into dispatch logic: an outage whose device can be tie
  back-fed is a **remote-switch quick win** (operator, no crew); otherwise it is a
  **field repair** needing a crew — crews ranked first, then by customers affected.

## Architecture

```
AMI last-gasp (telemetry.state) ─▶ oms._dark_meter_nodes ─┐
M1 model (grid_nodes/edges) ──────────────────────────────┼─▶ dms.outage_inference (M7)
customer→node map ────────────────────────────────────────┘          │
                                                                       ├─▶ /oms/outage/infer
M5 contingency (dms.contingency) ──────────────┐                       │
                                                ├─ dms.outage_validation (M8) ─▶ /oms/outage/validate
                                                └─ dms.crew_dispatch    (M9) ─▶ /oms/crew/recommend
```

Pure engines in `fastapi/dms/` (unit-tested standalone); thin endpoints in
`routers/oms.py` reusing the M1 loaders from `routers/dms.py`.

## Validation (shared platform DB never touched)

- **Pure unit tests: M7 4 · M8 4 · M9 3 = 11/11**; full suite **40 passed, 77
  skipped** (integration tests skip with no live API — nothing touched live).
- **Isolated-DB end-to-end (Abuja Site A):** a `LAST_GASP` for METER001 →
  - **M7**: probable device `E-BUS-METER`, feeding transformer `TX-01`, **3 customers**,
    confidence 1.0.
  - **M8**: consistent — M7's 3 customers == M5 N-1 `lost_customers` 3 (no mismatch).
  - **M9**: rank-1 `E-BUS-METER`, 3 customers, **dispatch_crew / field repair** (the
    meter line has no tie).

**Known interaction (documented):** during an outage a meter's last reading is the
last-gasp (0 kW), so the power-flow-based load at that node is 0 and M5 may classify
the element `secure` by *load*; the **customer** metrics (service-point counts) are
the reliable cross-check and agree (3 = 3). M9 correctly uses customers + tie
availability, not measured load.

## Integration follow-ups (flagged, deliberately NOT wired this pass)

Per the brief — natural reads from M2/M6 that are **not** trivial, held as follow-ups:

1. **M7 ↔ M6 fault location** — both localize topologically, but the objectives
   differ (M6 = best-Jaccard section; M7 = LCA covering *all* dark meters + customer
   estimation). Unifying them into one localization core is worthwhile but not a
   drop-in reuse.
2. **M7/M8 ↔ M2 state estimation** — estimated node voltage ≈ 0 would *corroborate*
   de-energization independent of AMI, raising confidence and catching meters that
   failed silently (no last-gasp). Needs the SE pipeline wired into the OMS path.
3. **M7 ↔ M6 impedance distance** — for a true *fault* (vs a planned/lateral outage),
   a measured fault current would pin distance-to-fault within the inferred section.

## Deployment / rollback

- No schema changes (M7–M9 are pure compute on the existing model + AMI signals; the
  M5 `lost_customers` field is additive in code).
- New engine modules + endpoints; rebuild/restart `diep-fastapi` to serve them
  (running app unaffected until then). Rollback = remove the three endpoints + engine
  modules (and the `lost_customers` field).

Commits preserved **un-squashed** (M7 → M8 → M9). Stacked on `main` (P4+P5 merged).
