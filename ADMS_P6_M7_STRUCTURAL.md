# DIEP ADMS P6-M7 — Structural-Graph Second Pass — Notes

**Branch:** `feature/adms-p6-m7-structural` → `main`
**Scope:** the unlock for M2↔M7 SE corroboration to be useful end-to-end.
**Read-only, additive, no new runtime deps, no schema changes, `.env` untouched.**

---

## What & why

Before this change M7 inferred outages only over the **energized tree** (closed
edges). When an outage was already *reflected in topology* — a protective device
(sectionalizer/recloser) had opened — the dark meters fell **outside** the energized
tree, so M7 produced no inference, and the M2 SE corroboration flags
(`corroborated_by_se`, `silent_failure_suspected`) had nothing to attach to.

Now M7 runs **two passes**:

1. **Energized (primary/authoritative)** — unchanged: dark meters still in the
   energized tree are localized by LCA per feeding transformer.
2. **Structural (fallback)** — over the **normally-closed network forced closed** (a
   tripped protective device is still "present"; normally-open ties excluded). A dark
   meter outside the energized tree is localized to the **open protective edge** on
   its path (the isolating device), with the affected section = everything
   structurally downstream of it.

A dark meter is handled by **exactly one** pass (energized if it is in the energized
tree, else structural), so the structural pass only fills the gap the energized pass
leaves — it never overrides an AMI-energized result. Each inferred outage now carries
a `source` field (`"energized"` | `"structural"`).

## Implementation

- `fastapi/dms/outage_inference.py` — factored the per-cluster inference into
  `_infer_pass(...)`; `infer()` builds the energized tree and a structural tree
  (`build_radial` fed the normally-closed edges with `is_closed` forced True, ties
  excluded) and routes dark meters to the right pass. `_isolating_open_edge(...)`
  finds the open protective device on the path for the structural case. Pure engine,
  no new deps.
- `fastapi/routers/dms.py` — `_se_edges` now also selects `normally_closed` (an
  **existing** column; additive read, **no schema change**) so the structural view
  can exclude ties.

## Validation

- **Host pure-test suite: 44 passed, 0 failed** — all P5/P6 engine tests, including
  the refactored M7 (existing 6 + 2 new) and every other pure unit test. The two new
  cases:
  - protective device open → dark meter outside the energized tree + SE collapse at
    that node ⇒ M7 yields a **structural** inference on the open device `E1` with
    `corroborated_by_se = true`;
  - same network with the device closed ⇒ the **energized** pass stays primary.
- **Direct host run of the exact scenario** confirmed end-to-end:
  `source=structural, probable_device=E1, feeding_transformer=TX, customers=3,
  corroborated_by_se=True`.

### Environment caveat (this session)

The Docker daemon became unresponsive partway through this session (even
`docker ps` / `docker inspect` hung), and the throwaway containers' `pip install`
could not reach PyPI. So two checks I normally run could **not** execute this pass:
the **full containerized `pytest`** and a **fresh isolated-DB** end-to-end run. These
are environment failures, **not** code issues. Mitigation used instead:

- Ran the pure unit tests **natively on the host** (no Docker/pip) → 44/44.
- Ran the exact structural scenario **natively on the host** → correct output.
- The only DB-touching change is an **additive `SELECT` of an existing column**
  (`normally_closed`), consumed by an engine that defaults it to `True` — trivially
  safe; the prior session already validated the SE-dead DB behaviour and the OMS
  endpoint wiring against a throwaway TimescaleDB.

No new throwaway DB/containers were left behind (their creation hung and never
succeeded this session); the live `diep-fastapi` was never touched.

**Recommendation:** re-run `pytest tests/ -q` and the `/oms/outage/infer` isolated-DB
check once the Docker/PyPI environment is healthy, to reconfirm the equivalent
pytest counts (expected ≈ 45 passed / 77 skipped) and the live endpoint path.

## Still-open follow-ups (not picked up, per the brief)

- **M7 ↔ M6 unification** (Jaccard best-match vs LCA-covering).
- **M6 impedance-distance refinement** for true faults.
