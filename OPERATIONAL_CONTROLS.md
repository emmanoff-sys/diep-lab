# DIEP ADMS Phase 2 — Operational Controls

Phase 2 moves DIEP from **decision support** (Phase 1, read-only) to **governed
actuation**. It is built safe-by-default: every control action — switch operation,
FLISR execution, Volt/VAR dispatch — flows through a single governed lifecycle with
approvals, interlocks, a feature-flag gate, and an immutable audit trail.

> **Scope:** actuation targets the **simulated grid model + simulators/mock DNP3
> RTU** via the existing command path. The governance is designed so real devices
> can attach later with no change to the control plane.

## Safety model (locked decisions)

- **Actuation target:** simulated grid + devices only (real-device-ready design).
- **Approval:** **two-person for high-risk** (switch ops, FLISR) — the approver must
  differ from the requester; **single-operator for low-risk** (e.g. in-band Volt/VAR).
- **Default posture:** master flag **`OC_CONTROLS_ENABLED` defaults OFF**, and every
  action defaults to **dry-run**. Live actuation requires the flag ON *and* an
  approved, explicitly-`live` action.

## Governance lifecycle (OC-1)

```
request ─▶ PENDING ─▶ (approve) ─▶ APPROVED ─▶ execute ─▶ EXECUTED ─▶ (rollback) ─▶ ROLLED_BACK
                  └▶ REJECTED                         └▶ FAILED
dry-run: request ─▶ PENDING ─▶ execute ─▶ EXECUTED   (plan + audit, NO actuation; flag not required)
live   : execute refused unless OC_CONTROLS_ENABLED=true AND status=APPROVED
```

Every transition appends to an **immutable audit log** (`control_audit`):
`REQUESTED · APPROVED · REJECTED · DRYRUN · EXECUTED · FAILED · ROLLED_BACK · BLOCKED`,
each with actor, timestamp, and detail. A blocked live attempt is itself audited.

### RBAC
- **Request / execute:** `operator`, `engineer`, `admin`.
- **Approve / reject / rollback:** `engineer`, `admin` (and ≠ requester for high-risk).
- **Read** (status, actions, audit): all roles. Tenant-scoped principals see only
  their own tenant's actions.

### Handler registry
Each `action_type` registers a `ControlHandler` with `plan()` (validate +
interlocks + before/preview), `execute()` (actuate → after_state), and `rollback()`.
The core knows nothing about grids — later modules plug in:

| Module | action_type | Risk | Status |
|---|---|---|---|
| OC-1 | `noop` | low | ✅ governance demonstrator (actuates nothing) |
| OC-2 | `switch_op` | high | ✅ governed switch operations (model + optional device) |
| OC-3 | `flisr` | high | ✅ governed FLISR execution (transactional switch sequence) |
| OC-4 | `voltvar_dispatch` | low/high | ✅ governed Volt/VAR dispatch (banded, rate-limited) |

> **Per-action risk:** a handler may override `risk_for(target, params)` to set risk
> from the request (OC-4 uses swing magnitude). The execute gate enforces the
> locked policy: **low-risk → single operator** (no separate approver needed);
> **high-risk → two-person** (must be APPROVED by a different actor). The master
> flag gates *all* live actuation regardless of risk.

## OC-4 — Volt/VAR dispatch (`voltvar_dispatch`, low/high-risk)

Translates a Volt/VAR lever — a target `setpoint_kw` on a controllable DER — into a
device command via the **proven DERMS command path** (`_dispatch_command`, reusing
`der.CURTAIL_MAP`: solar/EV→`set_limit`, battery→`set_power_limit`,
microgrid→`set_setpoint`).

**Request:** `target` = `der_id`, `params.setpoint_kw`, optional `params.override`.

**Safety shaping:**
- **Banded** — setpoint must be within `[0, rated_kw]`; out-of-band is blocked
  unless overridden (with a reason).
- **Rate-limited / risk-classified** — a swing within `OC_VOLTVAR_MAX_STEP_KW`
  (default 10) of *fresh* current output is **low-risk** (single operator); a larger
  swing is **high-risk** (two-person). Current output uses only telemetry fresher
  than `OC_VOLTVAR_FRESH_S` (default 600s); stale/missing data is treated as 0 kW so
  the classifier never under-estimates the swing.

Rollback re-dispatches the prior setpoint. Live dispatch reuses the validated
DERMS path and is gated by the master flag.

**Validated:** command mapping + band block + override; magnitude-based risk
(small in-band = low, large swing = high, robust to stale telemetry); unknown DER
404; high-risk two-person (self-approve 403, engineer approve, then flag-blocked).
The single-operator-low / two-person-high execute gate was validated flag-on
against an isolated DB.

## OC-2 — Switch operations (`switch_op`, high-risk)

Opens/closes a switchable `grid_edge` in the **network model** (the authoritative
switch state) and, when the edge is device-backed (`attrs.device_id`), dispatches
the breaker command via the existing command path (Kafka → dispatcher → MQTT →
device) and waits briefly for the ack (`OC_SWITCH_ACK_TIMEOUT_S`, default 8s; the
model remains authoritative if the ack times out).

**Request:** `target` = `edge_id`, `params.close` = `true|false`,
optional `params.override` = `true` (with a `reason`) to proceed past an interlock.

**Interlocks** (evaluated at plan time *and* re-checked at execute time; block
unless overridden):
1. **no-op** — edge already in the requested state;
2. **critical islanding** — opening would de-energize `critical`/`medical` customers;
3. **close-into-fault** — closing would re-energize a node with an active outage case;
4. **source paralleling** — closing would tie two already-energized sources.

The preview reports the affected energized set and `customers_lost`/`restored`.
Rollback restores the prior `is_closed` (and reverses the device command if one
was sent).

**Validated:** all four interlocks block at request time; override bypasses while
the preview still records the risk; dry-run never mutates the model; live execute
is refused while the flag is off. Live execute + rollback (model True→False→True)
and the TOCTOU/no-op guard were validated against an isolated seeded DB so the
running platform stayed in its flag-off posture.

## OC-3 — FLISR execution (`flisr`, high-risk)

Promotes the read-only DMS FLISR planner into a governed, **transactional**
restoration. It reuses `dms.plan_flisr` to compute the isolation + restoration
switch sequence (isolate the fault at the nearest upstream switch; back-feed lost
load via a normally-open tie *without* re-energizing the fault), then executes that
sequence atomically: any failure mid-sequence reverts every switch already moved.

**Request:** `target` = fault node (or `params.fault_edge`). The preview reports
`isolated_edges`, `restored_edges`, customers lost/restored/still-out, the step
plan, and `restores_all`.

**Execute:** opens the isolating switch, closes the restoring tie(s), and writes a
`flisr_events` row (`executed=true`). **Rollback** restores the pre-FLISR switch
state captured at plan time. The planner's safety property — it will not
re-energize the faulted node — is preserved (e.g. a bus fault yields
`restored_edges=[]`, `restores_all=false`).

**Legacy path closed:** `POST /dms/flisr/simulate` with `execute=true` (the
pre-Phase-2 ungoverned mutation) now also requires `OC_CONTROLS_ENABLED`; the
sanctioned live path is the governed `flisr` control action. `execute=false`
(planning) is unchanged.

**Validated:** governed plan/preview matches the DMS planner; dry-run does not
actuate; the bus-fault safety case refuses restoration; live execute is two-person
approved then flag-blocked. Live execute (E-SW-01→open, E-TIE-01→close) +
`flisr_events` write + full rollback validated against an isolated seeded DB.

## API (`/controls`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/controls/status` | any | flag state, registered types, approval model |
| POST | `/controls/actions` | operator+ | request an action (runs plan/interlocks; PENDING) |
| POST | `/controls/actions/{id}/approve` | engineer+ | approve (≠ requester for high-risk) |
| POST | `/controls/actions/{id}/reject` | engineer+ | reject |
| POST | `/controls/actions/{id}/execute` | operator+ | dry-run always; live needs flag + APPROVED |
| POST | `/controls/actions/{id}/rollback` | engineer+ | best-effort revert via before_state |
| GET | `/controls/actions[/{id}]` | any | list / detail (+ audit) |
| GET | `/controls/audit` | any | audit trail |

## Data model (`sql/018_operational_controls.sql`)

- `control_actions` — lifecycle record (type, target, params, mode, risk, status,
  requested_by/approved_by, before/after state, tenant, timestamps).
- `control_audit` — append-only transition log.

Additive + idempotent, applied by `init-db.sh`.

## Validation (OC-1)

Live, against the running platform (flag default OFF):
- viewer cannot request (403); operator cannot approve (403).
- dry-run runs the full lifecycle to EXECUTED with controls disabled.
- live action: operator requests → **engineer approves** (two-person) → execute is
  **BLOCKED (403)** by the OFF flag; audit shows `REQUESTED → APPROVED → BLOCKED`.
- Regression: 32/32 smoke tests (5 new in `tests/test_controls_smoke.py`).

## Enabling live actuation (operators)

Live control is intentionally inert until explicitly enabled:
1. Set `OC_CONTROLS_ENABLED=true` (env) — gates all live execution.
2. Request an action with `"mode":"live"`, get it approved (two-person for
   high-risk), then execute. Dry-run first is strongly recommended.
