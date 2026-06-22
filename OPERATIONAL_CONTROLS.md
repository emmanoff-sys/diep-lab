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
| OC-5 | *(GUI layer)* | — | ✅ operational console: arm / approve / execute / rollback + audit, role-gated |
| OC-6 | *(observability)* | — | ✅ audit export, readiness/history reports, Prometheus metrics + alerts |

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

## OC-5 — Operational GUI (portal)

Promotes the three read-only OMS panels into **governed control surfaces** without
giving any of them the power to actuate. Every operator gesture flows through the
OC-1 lifecycle; the portal only *requests / approves / executes* governed actions
and renders their state. Live actuation remains gated server-side by the master
flag — the GUI surfaces that gate (and its refusals), it never bypasses it.

**On the OMS page (`/oms`):**
- **Operational-controls console** (`OperationalControls.tsx`) — a single
  governed surface with:
  - a **posture banner** with a hard **SAFE** (green) vs **LIVE** (red) state
    driven by `GET /controls/status` (`OC_CONTROLS_ENABLED`), plus the caller's
    role and what they may do;
  - a **switch-operations** arm strip (the map overlay stays read-only; control
    lives here) listing switchable edges with their open/closed state;
  - a live **control action queue** (`GET /controls/actions`, 5s poll) showing
    type / target / mode / risk / status / requester / approver, with **role-gated
    governed buttons** (Approve · Reject · Execute · Rollback) whose visibility
    mirrors the server's rules (operator+ to request/execute, engineer+ to
    approve, and a high-risk action's requester cannot self-approve);
  - an inline **audit drawer** per action (`GET /controls/actions/{id}` → `audit`).
- **Arm affordances** on the decision-support panels:
  - the **FLISR planner** gains an *Arm FLISR action* button on the rendered plan
    (`flisr`, high-risk);
  - the **Volt/VAR** panel gains a governed **dispatch** sub-surface (controllable
    DER + setpoint → `voltvar_dispatch`); the advisory above it stays read-only;
  - the **switch** strip arms `switch_op`.
- **Arm/confirm modal** (`ControlActionModal.tsx`) — the operator picks **dry-run
  vs live**, sees the risk/approval implication and the flag-off warning, and
  confirms. Confirming only *requests* the action (`POST /controls/actions`) — it
  actuates nothing; the queue then drives approve/execute. **Live** mode is styled
  hard-red and spells out the two-person rule and the master-flag gate.

**Visual safety states:** SAFE/LIVE banner; live queue rows carry a red left
border and a `live` badge; dry-run rows a muted badge; status is colour-coded
(PENDING amber · APPROVED blue · EXECUTED green · REJECTED/ROLLED_BACK grey ·
FAILED red). Role gating is client-side for affordance *and* enforced server-side.

**Client wiring:** `lib/controls.ts` (typed `/controls/*` client, SWR hooks,
`canRequest`/`canApprove`/`affordances` gates). The BFF (`/api/diep/*`) forwards
the caller's own JWT, so the portal's RBAC is FastAPI's RBAC.

**Validated (flag OFF, live platform):** signed in as `engineer`, the console
renders **SAFE**; arming a switch op opens the confirm modal (high-risk · two-
person) in both dry-run and live styling; the queue lists real governed actions
with correct status colours and role-appropriate buttons; the FLISR plan exposes
*Arm FLISR action* and the Volt/VAR dispatch surface lists controllable DERs.
Screenshots in [`docs/oms-operational-controls/`](docs/oms-operational-controls/)
(`oc5-console`, `oc5-flisr-arm`, `oc5-arm-modal`, `oc5-arm-modal-live`,
`oc5-queue`, `oc5-full`). Backend regression unchanged at **51/51** (OC-5 is
portal-only).

## OC-6 — Operational audit & safety reporting

Makes the control plane **observable and alertable**. Every governed transition
already writes the immutable `control_audit` row (OC-1); OC-6 fans that same
choke-point out to **Prometheus** and adds **reporting/export** endpoints and a
portal readiness panel — without changing the governance semantics.

**Prometheus metrics** (on the FastAPI default registry → scraped by the existing
`/metrics` job):
- `diep_control_events_total{event,action_type,risk}` — counter, one per
  lifecycle transition (`REQUESTED·APPROVED·REJECTED·DRYRUN·EXECUTED·FAILED·
  BLOCKED·ROLLED_BACK`).
- `diep_control_live_blocked_total{action_type,reason}` — live executes refused
  by a gate (`flag_off` | `needs_approval`). The key "someone tried to actuate
  while gated" signal.
- `diep_controls_enabled` — gauge, 1 when `OC_CONTROLS_ENABLED`.
- `diep_control_actions{status}` — gauge, current queue depth by status.

Gauges refresh after every mutating endpoint (and on the readiness report), so the
scrape itself does no DB work. Safety-relevant events (`BLOCKED·FAILED·
ROLLED_BACK`, and every **live EXECUTED**) are also logged at WARNING for
log-based alerting independent of the metrics pipeline.

**Prometheus alert rules** (`prometheus/alerts.yml`, group
`diep-operational-controls`, routed via the existing severity tree):
`ControlActionFailed`, `ControlLiveExecuteBlocked`, `OperationalControlsEnabled`
(LIVE posture surfaced), `ControlActionRolledBack`, `ControlApprovalsBacklog`.

**Reporting endpoints:**
- `GET /controls/report/readiness` — control-readiness / safety snapshot: posture
  (SAFE/LIVE), queue counts, `awaiting_approval`/`awaiting_execution`, oldest
  pending age, 24h activity (from the audit trail), and human-readable
  `warnings` + a `ready` flag. Also refreshes the gauges.
- `GET /controls/report/history` — filtered action history (`action_type`,
  `status`, `risk`, `since_hours`) plus aggregates by type / status / mode /
  requester.
- `GET /controls/audit/export?format=csv|json` — downloadable audit trail (CSV
  default, `Content-Disposition: attachment`) joined to each action's metadata.

All reporting is read-role + tenant-scoped (a tenant principal sees only its own).

**Portal:** the OMS operational-controls console gains a **Control readiness &
safety** panel (`ControlReadiness.tsx`) — posture/READY badge, queue + 24h stats,
readiness warnings, and a one-click **Export audit (CSV)** download.

**Validated (flag OFF, live platform):** readiness returns `SAFE` with correct
counts and warnings; history filters + aggregates; CSV export emits the right
header + `Content-Disposition`; `/metrics` exposes all four control-plane series;
viewer can read, anonymous is rejected. Prometheus loaded all five alert rules
(`promtool` 23 rules OK), `ControlApprovalsBacklog` correctly went *pending*
against the real backlog while the rest stayed inactive. Regression **58/58**
(7 new in `tests/test_oc_report_smoke.py`). Readiness panel screenshot:
[`docs/oms-operational-controls/oc6-readiness.png`](docs/oms-operational-controls/oc6-readiness.png).

## Phase 3 — Real-device control (the DNP3 RTU)

Phase 3 brings a real(istic) field device — the **DNP3 RTU MGD900** — fully under
the Phase-2 governance, end-to-end, with protocol-level confirmation. It exploits
the fact that the OC handlers are **device-agnostic**: they act on `der_assets` /
`grid_edges` + the command path, so onboarding a device is mostly data.

### P3-1 — RTU governability (data only, no handler changes)
Migration `sql/019_rtu_governable.sql` closes the M7 gap:
- registers **MGD900 as a controllable `microgrid` DER**, so OC-4
  `voltvar_dispatch` can target its setpoint (→ `set_setpoint`, the DNP3 analog
  output);
- models its **grid-tie breaker as a switchable, device-backed edge**
  `E-MGD900-CB` (BUS-01 → ND-MGD900). OC-2 `switch_op` already maps a device-backed
  **open → `island`** / **close → `grid_connect`** (the microgrid breaker
  vocabulary), so islanding and resynchronized reconnect are now governed actions.

### P3-2 — Command-echo verification (`routers/device_state.py`)
Closes the loop on actuation. A device can **ACK a command and still not move** (a
stuck breaker, a clamped/rejected setpoint). After a live actuation the handler now
reads the device's *reported* state back from telemetry and confirms it reached the
commanded state:
- **`switch_op` — hard gate:** after dispatching the breaker command it verifies the
  device's reported `grid_connected` matches the commanded position. On a real
  divergence it **reverts the model** (so model and field agree) and **FAILs** the
  action; the audit records the divergence.
- **`voltvar_dispatch` — soft gate:** verifies the device converged to the setpoint
  *only if the device echoes one* (the RTU publishes `setpoint_kw`; most DERs don't —
  those are an un-enforceable skip, never a false failure).

`verify_echo` is tri-state: **confirmed** (a fresh post-command reading matched),
**diverged** (reported but never reached target → fail), or **unverifiable** (device
doesn't report the field → skip). Tunables: `OC_VERIFY_ECHO` (default on),
`OC_ECHO_TIMEOUT_S` (12), `OC_ECHO_SETPOINT_TOL_KW` (1).

**Validated:** the readback + matcher against the **live RTU** (confirm vs real
divergence); and the full governed flow on an **isolated DB** (flag on) — a confirmed
breaker open → EXECUTED with `echo.confirmed`, rollback restores; a device that never
moves → action **FAILED with the model reverted to closed**. Regression unchanged.

### P3-3 — Pluggable DNP3 transport (`drivers/dnp3/transport.py`)
The DNP3 driver is transport-agnostic, so the *same* governed path runs over either:
- the in-process **mock outstation** (default, no dependency), or
- a real **DNP3/TCP master** (`pydnp3`/opendnp3) against field hardware.

Selection is by config — `transport: "mock" | "tcp"` (inferred from `host` when
omitted: a real address ⇒ tcp). `pydnp3` is imported **lazily** (only when the real
transport is selected) and its absence raises a clear, actionable error. The real
master integrity-scans the outstation into a measurement cache for reads and issues
CROB (breaker) / AnalogOutput (setpoint) controls with **select-before-operate**.
Pointing a device at hardware is a config edit, not a code change.

### P3-4 — Real-device control in the GUI
The RTU's breaker and setpoint auto-appear in the OC-5 console (it is governable);
P3-4 makes the loop visible: the action queue shows a **command-echo badge**
(`device ✓` confirmed / `device ✗` diverged / `echo n/a` unverifiable) from
`after_state.echo`, and **device-backed switches are tagged** with their bound
device + protocol (e.g. `DNP3 ▸ MGD900`) read from the edge `attrs`.

**Validated:** DNP3 driver selftest (mock read/normalize/controls + transport
selection + graceful pydnp3-absent guard) PASSED; the live edge agent runs the mock
transport and the RTU keeps publishing; portal typecheck clean; regression **65/65**.

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
| GET | `/controls/report/readiness` | any | OC-6 readiness / safety snapshot |
| GET | `/controls/report/history` | any | OC-6 filtered history + aggregates |
| GET | `/controls/audit/export` | any | OC-6 audit export (CSV / JSON) |

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
