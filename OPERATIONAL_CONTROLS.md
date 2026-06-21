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
| OC-3 | `flisr` | high | planned |
| OC-4 | `voltvar_dispatch` | low/high | planned |

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
