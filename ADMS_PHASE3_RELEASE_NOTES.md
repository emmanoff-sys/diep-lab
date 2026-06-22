# DIEP ADMS Phase 3 — Real-Device Control — Release Notes

Branch: `feature/adms-realdevice-control` → `main`
Scope: bring a real(istic) field device — the **DNP3 RTU MGD900** — fully under the
Phase-2 governed control plane, end-to-end, with **protocol-level confirmation** and
a **pluggable transport** that swaps the in-process simulator for real DNP3 hardware
by configuration.

All changes are **additive and backwards-compatible**: one idempotent SQL migration,
one new FastAPI helper module, additive handler logic, a refactored (still
mock-default) DNP3 driver, and portal additions. **Live actuation stays inert by
default** — it still requires `OC_CONTROLS_ENABLED` and an approved live action.
`.env` was not modified.

---

## Why this matters

Phase 2 made actuation *governed*; Phase 3 makes it *real and verified*. The
governance handlers were written device-agnostic, so onboarding the RTU was mostly
data — and the new safety property is that a governed action now confirms the **field
device actually reached the commanded state**, not merely that it ACK'd.

## What shipped (P3-1 … P3-4)

| Module | Commit | Summary |
|---|---|---|
| **P3-1** RTU governability | `df3a0b8` | Migration `019`: register MGD900 as a controllable microgrid DER and model its grid-tie breaker as a switchable, device-backed edge `E-MGD900-CB`. OC-2 maps open→`island` / close→`grid_connect`; OC-4 maps the setpoint→`set_setpoint`. **No handler changes.** |
| **P3-2** Command-echo verification | `930f9a5` | `routers/device_state.py`: tri-state `verify_echo()`. `switch_op` (hard gate) reverts the model + FAILs on breaker divergence; `voltvar_dispatch` (soft gate) enforces setpoint convergence only when the device echoes one. DNP3 driver publishes `setpoint_kw`. |
| **P3-3** Pluggable DNP3 transport | `a1fa232` | `drivers/dnp3/transport.py`: `Dnp3Transport` + `make_transport()` factory + `RealDnp3Master` (pydnp3/opendnp3, CROB + AnalogOutput, select-before-operate). Mock stays default; `pydnp3` lazy-imported with a clear absent-error. |
| **P3-4** GUI surface | `16fa7a5` | Action-queue command-echo badge (`device ✓ / ✗ / n/a`); device-backed switches tagged with device + protocol (`DNP3 ▸ MGD900`). |

## Safety model (unchanged from Phase 2, now device-closed)

- Master flag **OFF** by default; **dry-run** default; **two-person** for high-risk.
- New: **echo verification** — `switch_op` is a *hard gate* (a breaker that does not
  confirm ⇒ model reverted to match the field + action FAILED); `voltvar_dispatch`
  is a *soft gate* (only enforced when the device reports a setpoint). Tunables:
  `OC_VERIFY_ECHO` (on), `OC_ECHO_TIMEOUT_S` (12), `OC_ECHO_SETPOINT_TOL_KW` (1).

## Real hardware (P3-3)

A device runs against field hardware by config, with no code change:
```json
{ "device_id": "MGD900", "protocol": "dnp3",
  "config": { "host": "10.0.0.5", "port": 20000, "transport": "tcp",
              "outstation_addr": 1024, "scan_seconds": 5 } }
```
`pydnp3` must be installed where real outstations are reached; the lab default
(`host: "mock"`) needs nothing.

## Validation

- **Regression 65/65** smoke tests (flag OFF). New: `test_p3_rtu_governable` (5),
  `test_p3_echo_verify` (2).
- **DNP3 driver selftest** PASSED — mock read/normalize/controls, transport
  selection (mock default, tcp for real hosts), and the graceful pydnp3-absent guard.
- **Echo verification** proven against the **live RTU** (confirm vs real divergence)
  and end-to-end on an **isolated DB** (flag on): confirmed open → EXECUTED →
  rollback restores; device-doesn't-move → FAILED with the model reverted.
- **Live edge agent** runs the mock transport (`DNP3 link up via MockDnp3Outstation`)
  and the RTU keeps publishing telemetry; portal typecheck clean.
- Screenshots: [`docs/oms-realdevice-control/`](docs/oms-realdevice-control/).

## Deployment / migration

- Apply `sql/019_rtu_governable.sql` (idempotent; wired into `init-db.sh`).
- Run the DNP3 edge agent (`docker-compose-dnp3.yml`) for the RTU to be live.
- No change to existing services; `OC_CONTROLS_ENABLED` absent ⇒ safe (OFF).

Design reference: [`OPERATIONAL_CONTROLS.md`](OPERATIONAL_CONTROLS.md) (Phase 3 section).
Commits are preserved **un-squashed and un-rebased** (P3-1 → P3-4).
