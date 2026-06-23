# DIEP ADMS Phase 6 — Follow-ups — Notes

**Branch:** `feature/adms-p6-followups` → `main` (post-#11)
**Scope:** two small, targeted follow-ups from the Phase 6 review. **Read-only,
additive, no new runtime deps, no schema, `.env` untouched.**

---

## Follow-up 1 — M5 last-gasp load fallback

**Problem.** A meter in AMI last-gasp reports ~0 kW, so M5's *load-based*
classification treated its outage as `secure` ("no load lost") even though customers
were out — the 3=3 case found in the Phase 6 review.

**Fix (minimal).** `dms.contingency.analyze` gains an optional `load_floor`
(node_id → fallback kW), applied **only** to the load-based classification sums
(`lost_load`, `unserved_load`) — **not** the power flow, and **not** the ranking
formula. The adapter `dms._lastgasp_load_floor()` supplies each last-gasp meter's M1
base load; both `GET /dms/contingency/n1` and the OMS M8/M9 path
(`oms._infer_and_n1`) pass it. Customer counts (the reliable signal) are untouched.

**Validation.** Unit `test_p5_contingency.py` (5/5) incl. the exact case; isolated-DB
Abuja: `E-BUS-METER` without floor `secure`/0 kW → with floor **`unserved`/80 kW**,
customers **3 = 3** unchanged.

## Follow-up 2 — M7 ↔ M2 state-estimation corroboration

**Goal.** Use M2 state estimation as a **secondary** signal in M7 outage inference —
never overriding the AMI-based result — to corroborate de-energization and surface
silent meter failures. Adds two flags only:
- `corroborated_by_se` (per inferred outage) — SE agrees a dark meter is dead.
- `silent_failure_suspected` / `silent_failure_nodes` (top level) — meters SE reads
  dead that did **not** report a last-gasp.

**Wiring.** Trivial — no new deps, no schema. The engine
(`dms.outage_inference.infer`) takes an optional `se_dead_nodes` set and stays pure;
`oms._se_dead_nodes()` runs M2 (`se.estimate`) + a per-unit floor, **best-effort**
(any SE error → `se_available=false`, inference unaffected). Scope honored: flags
only, **no change to M7's inference logic**.

**Documented interaction (held as a follow-up — deliberately NOT pushed through).**
SE marks a node "dead" only when (a) the model shows it unenergized — i.e. a
protective device opened and that's reflected in SCADA topology — or (b) the
estimator computes a genuine deep voltage collapse. For a **bare last-gasp on an
otherwise-closed model**, the LinDistFlow WLS estimates ~1.0 pu (it does **not**
trust the 0 V reading — correct behaviour, the reading becomes a flagged residual).
And once the outage **is** reflected in topology (switch open), the dark meter falls
*outside* M7's energized tree (M7 builds over closed edges), so M7 currently produces
no inference to attach the flag to. Making corroboration fire alongside M7's
inference in that case requires M7 to build over the **structural** (not just closed)
graph — a separate, larger change, left as a follow-up.

**Validation.** Unit `test_p6_outage_inference.py` (6/6) covers the flags +
silent-failure + default-off; isolated-DB Abuja: SE correctly marks the de-energized
section dead when `E-SW-01` is open, and estimates ~1.0 pu / `se_dead=[]` on the
closed model — both as designed.

## Still-open follow-ups (not in this pass, per the brief)

- **M7 ↔ M6 unification** (Jaccard best-match vs LCA-covering) — documented, later.
- **M6 impedance-distance refinement** — documented, later.
- **M7 structural-graph inference** (new, surfaced above) — needed for SE
  corroboration to fire on a topology-reflected outage.

## Test summary

Full suite: **43 passed, 77 skipped** (integration tests skip with no live API — the
shared `diep-fastapi` was never touched). Commits are granular per follow-up,
un-squashed.
