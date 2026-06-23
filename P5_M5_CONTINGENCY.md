# DIEP ADMS P5-M5 — N-1 Contingency Analysis — Design & Validation

**Phase:** 23 (P5 continuation) · **Module:** M5 — N-1 Contingency
**Branch:** `feature/adms-p5-advanced-dms-cont` · **Status:** implemented + validated
**Classification:** additive, **read-only**. No actuation, no flags.

---

## 1. Objective

Assess whether the feeder is **N-1 secure**: for every credible single-element
outage (each in-service line / transformer / switch / tie), determine what load is
lost, whether **ties can back-feed** it (FLISR-style restoration), whether the
post-contingency network has **voltage/thermal violations**, and **rank** the
contingencies by severity. This is the planning view behind FLISR and switching
decisions.

## 2. Method

For each in-service element:
1. **Open the element** and recompute the energized set from the substation; the
   difference is the lost section.
2. **Restore** greedily: close available open ties/switches that re-energize lost
   nodes *without* re-energizing through the failed element and *keeping the network
   radial* (`_is_radial`). Mirrors the existing FLISR planner.
3. **Post-contingency power flow** (M3) on the restored network → voltage/thermal
   violations.
4. **Classify & score:** `unserved_load_kw·1000 + violations·100 + lost_load(if restored)`.

**Classification:** `secure` (nothing lost) · `restorable` (lost load fully
back-fed) · `partial` (some restored, some stranded) · `unserved` (lost, no
back-feed) · `violation` (service kept but a limit is breached — e.g. losing a DER
that was supporting voltage).

**Load vs generation.** Lost **load** (positive injection) and lost **generation**
(DER, negative injection) are reported separately, so stranding a DER shows as
`lost_generation_kw` (and possibly a `violation`), not negative "lost load".

## 3. Architecture & integration

```
_se_nodes/_se_edges (M1) ─┐
_pf_loads ────────────────┼─▶ contingency.analyze()
_customers_by_node ───────┘     for each element: open → _restore (ties) → pf.solve
                  GET /dms/contingency/n1 (read) ─▶ operators / planning / FLISR
```

Pure engine [fastapi/dms/contingency.py](fastapi/dms/contingency.py); adapter +
endpoint in [routers/dms.py](fastapi/routers/dms.py). Read-only; no Kafka/actuation/flags.

## 4. Validation

**Unit tests** [tests/test_p5_contingency.py](tests/test_p5_contingency.py) — 4/4:
a tied segment is `restorable` (back-fed via the tie, 0 unserved); an un-tied segment
is `unserved` (load + customers stranded); losing the source feed strands the whole
subtree but a single tie back-feeds all of it through the still-closed intra-subtree
edges; not N-1 secure, and contingencies are severity-ranked.

**Isolated-DB end-to-end (Abuja Site A, 10 elements):** `n1_secure=false`. Findings:

| Element | lost kW | restored by | unserved kW / cust | class |
|---|---|---|---|---|
| E-BUS-METER | 78.0 | — | 78.0 / 3 | unserved |
| E-SUB-FDR (source) | 85.2 | — | 85.2 / 3 | unserved |
| E-BUS-EV | 7.2 | — | 7.2 / 0 | unserved |
| **E-SW-01** | 85.2 | **E-TIE-01** | 0 | **restorable** |
| **E-TX-BUS** | 85.2 | **E-TIE-01** | 0 | **restorable** |
| E-BUS-BAT/INV/MG | 0 | — | 0 | violation (DER support lost) |
| E-MGD900-CB | 0 | — | 0 | secure |

The TX-01 path failures (`E-SW-01`, `E-TX-BUS`) are correctly identified as **fully
restorable via the TX-02 tie `E-TIE-01`** — exactly the FLISR back-feed scenario —
while the meter and source losses (no alternate feed) are the worst-ranked
contingencies, and losing a voltage-supporting DER surfaces as a `violation`.

## 5. Rollback / risk / extensions

- **Rollback:** remove the endpoint + `fastapi/dms/contingency.py`. Additive; nothing
  existing touched.
- **Risk:** read-only; bounded by element count × power-flow solves (10 here).
- **Extensions:** N-1-1 / double contingencies; probabilistic risk (failure rates ×
  severity); thermal-overload-aware restoration (shed/curtail to clear violations);
  auto-generate pre-armed FLISR plans for the restorable contingencies.
