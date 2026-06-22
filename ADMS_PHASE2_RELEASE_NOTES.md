# DIEP ADMS Phase 2 — Operational Controls — Release Notes

Branch: `feature/adms-operational-controls` → `main`
Scope: move DIEP from **decision support** (Phase 1, read-only ADMS) to
**governed actuation** — FLISR execution, switch operations, and Volt/VAR
dispatch — behind a single safety-first governance core, an operational GUI, and
an audit/observability layer.

All changes are **additive and backwards-compatible**: one new idempotent SQL
migration, new FastAPI routers + endpoints, new portal components, new Prometheus
metrics/alerts, and new tests. No existing endpoint, schema object, or running
service was removed or repurposed. **Live actuation is inert by default** — it
requires an explicit, off-by-default master flag *and* an approved live action.

---

## Safety posture (locked, and held throughout the build)

- **Master flag `OC_CONTROLS_ENABLED` defaults OFF** — gates *all* live actuation.
  Dry-run planning and the entire governance API stay available with it off.
- **Dry-run by default.** Every action is dry-run unless explicitly `live`.
- **Two-person for high-risk** (switch ops, FLISR) — the approver must differ from
  the requester; **single-operator for low-risk** (in-band Volt/VAR).
- **Actuation target:** the simulated grid model + simulators / mock DNP3 RTU via
  the existing command path. The control plane is real-device-ready by design.
- **Immutable audit** of every transition; a blocked live attempt is itself audited.

Throughout development, all **live execute + rollback** paths were validated on
**isolated, ephemeral TimescaleDB instances** so the running platform never left
its flag-OFF posture. `.env` was not modified.

---

## What shipped (OC-1 … OC-6)

| Module | Commit | Summary |
|---|---|---|
| **OC-1** Governance core | `af341bb` | `control_actions` lifecycle + `control_audit`, handler registry, flag gate, dry-run default, two-person SoD, `/controls/*` API, `noop` demonstrator. |
| **OC-2** Switch operations | `136e5e3` | `switch_op` (high-risk): opens/closes a switchable `grid_edge` (+ optional device breaker command). Interlocks: no-op, critical/medical islanding, close-into-fault, source paralleling — checked at plan **and** execute. |
| **OC-3** FLISR execution | `93345f1` | `flisr` (high-risk): reuses the read-only planner, applies the isolate+restore switch sequence **transactionally** (revert-on-failure), writes `flisr_events`. Legacy `/dms/flisr/simulate?execute=true` now also flag-gated. |
| **OC-4** Volt/VAR dispatch | `9dfcfdc` | `voltvar_dispatch` (low/high): DER setpoint → device command via the proven DERMS path; **banded** `[0, rated]`; risk by swing magnitude with a **fresh-telemetry** rate-limiter (single-op vs two-person). |
| **OC-5** Operational GUI | `6f5c9f0` | Promotes the three read-only OMS panels into governed control surfaces: arm → request → approve → execute → rollback, a live action queue, per-action audit drawer, hard SAFE/LIVE visual states, role-gating (client + server). |
| **OC-6** Audit & safety reporting | `3a71179` | Prometheus control-plane metrics + alert rules; readiness/history reports; CSV/JSON audit export; portal readiness panel. |

### Data model (`sql/018_operational_controls.sql`)
- `control_actions` — lifecycle record (type, target, params, mode, risk, status,
  requested_by / approved_by, before/after state, tenant, timestamps).
- `control_audit` — append-only transition log.
Additive + idempotent; applied by `init-db.sh`.

### Governance lifecycle
```
request ─▶ PENDING ─▶ (approve) ─▶ APPROVED ─▶ execute ─▶ EXECUTED ─▶ (rollback) ─▶ ROLLED_BACK
                  └▶ REJECTED                          └▶ FAILED
dry-run: request ─▶ PENDING ─▶ execute ─▶ EXECUTED     (plan + audit, NO actuation; flag not required)
live   : execute refused unless OC_CONTROLS_ENABLED=true AND (high-risk ⇒ APPROVED)
```

### Observability (OC-6)
- Metrics on `/metrics`: `diep_control_events_total{event,action_type,risk}`,
  `diep_control_live_blocked_total{action_type,reason}`, `diep_controls_enabled`,
  `diep_control_actions{status}`.
- Alerts (`prometheus/alerts.yml`, group `diep-operational-controls`):
  `ControlActionFailed`, `ControlLiveExecuteBlocked`, `OperationalControlsEnabled`,
  `ControlActionRolledBack`, `ControlApprovalsBacklog`.
- Reports: `/controls/report/readiness`, `/controls/report/history`,
  `/controls/audit/export` (CSV/JSON). Read-role + tenant-scoped.

---

## Validation

- **Regression: 58/58** smoke tests green against the live platform (flag OFF).
  New suites: `test_controls_smoke` (5), `test_oc_switch_smoke` (7),
  `test_oc_flisr_smoke` (6), `test_oc_voltvar_smoke` (6), `test_oc_report_smoke` (7).
- **Live actuation** (execute + rollback) for OC-2/3/4 validated on **isolated
  ephemeral DBs**; the shared platform stayed flag-OFF.
- **GUI** validated via Playwright as `engineer` — SAFE console, arm/confirm modal
  (dry-run + LIVE styling), populated governed queue, FLISR arm, Volt/VAR dispatch
  surface, and the OC-6 readiness panel. Screenshots in
  [`docs/oms-operational-controls/`](docs/oms-operational-controls/).
- **Alerts** loaded into Prometheus (`promtool` OK); `ControlApprovalsBacklog`
  correctly went *pending* against the real backlog while the rest stayed inactive.

---

## Enabling live actuation (operators)

Live control is intentionally inert until explicitly enabled:
1. Set `OC_CONTROLS_ENABLED=true` (env) — gates all live execution.
2. Request an action with `"mode":"live"`; for high-risk get it **approved by a
   different user**; then execute. Dry-run first is strongly recommended.

Optional tunables: `OC_SWITCH_ACK_TIMEOUT_S` (default 8),
`OC_VOLTVAR_MAX_STEP_KW` (10), `OC_VOLTVAR_FRESH_S` (600).

---

## Migration / deployment

- Apply `sql/018_operational_controls.sql` (idempotent; already wired into
  `init-db.sh`). No data backfill required.
- Restart `diep-fastapi` to load the new routers; reload Prometheus to pick up the
  new alert rules.
- No change to existing services; `OC_CONTROLS_ENABLED` absent ⇒ safe (OFF).

Full design reference: [`OPERATIONAL_CONTROLS.md`](OPERATIONAL_CONTROLS.md).

Commits are preserved **un-squashed and un-rebased** (OC-1 → OC-6).
