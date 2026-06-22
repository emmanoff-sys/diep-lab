# DIEP ADMS Phase 4 — Closed-Loop Automation — Release Notes

Branch: `feature/adms-closedloop-automation` → `main`
Scope: let DIEP act on its own analysis — **automatically** — but only ever through
the Phase-2/3 governed control plane (approvals, flag gate, echo verification,
audit). The defining principle: closed-loop automation is **opt-in, bounded, and
human-in-the-loop by default**.

All changes are **additive and backwards-compatible**: one idempotent SQL migration,
new FastAPI routers, a refactored-for-reuse `submit_action`, portal additions, and an
**opt-in** controller service. `.env` was not modified. The engine is inert until an
operator explicitly enables it.

---

## The two-flag safety model

| Outcome | Requires |
|---|---|
| Engine evaluates policies | `OC_AUTOMATION_ENABLED=true` |
| A policy is considered | that policy `enabled=true` |
| A policy **proposes** (governed PENDING action, no actuation) | mode `recommend` (default) |
| A policy **auto-executes** | mode `auto` **and** `OC_CONTROLS_ENABLED=true` **and** within the policy's bounds |

Plus per-policy **cooldown**, a **circuit breaker** (trips a policy after repeated
failures), and — for switch/breaker actions — **P3-2 echo verification** (a device
that doesn't move => FAILED + revert). Every auto action runs the same governed
lifecycle as an operator's, including the **two-person rule** (a distinct
`automation:supervisor` identity approves high-risk actions).

## What shipped (P4-1 … P4-4)

| Module | Commit | Summary |
|---|---|---|
| **P4-1** Engine foundation | `d9ea3ee` | `automation_policies`/`automation_events`; the governed tick orchestrator (recommend/auto, cooldown, circuit breaker); `/automation/{status,policies,tick,events}`; `controls.submit_action` refactor; noop demonstrator. |
| **P4-2** FLISR auto-mode | `7e0d619` | `flisr` policy: propose/auto governed restoration on restorable outages; never auto load-sheds; bounded by `require_restores_all` + `max_customers`; de-dup. |
| **P4-3** Continuous Volt/VAR | `ce0e559` | `voltvar` policy: bounded governed DER dispatch on a voltage violation; rate-limit-aware (only auto-executes OC-4 low-risk swings). |
| **P4-4** Automation GUI | `1f206ea` | AutomationConsole: posture banner, policy enable/mode toggles (engineer), tripped+Reset, activity feed; `auto` tag on engine-created actions. |

Plus the opt-in **controller** (`automation/controller.py`,
`docker-compose-automation.yml`) that ticks the engine on an interval.

## Validation

- **Regression 72/72** (flag OFF). New: `test_p4_automation_smoke` (engine inert
  while disabled, policies seeded disabled, role gating, flisr/voltvar registered).
- **Isolated DB** (flags on), per policy:
  - **noop**: recommend => governed PENDING + 'proposed'; cooldown => skip; auto => EXECUTED.
  - **FLISR**: recommend; dedup (no duplicate); bounds => blocked (no switch moved);
    auto => EXECUTED (E-SW-01 open, E-TIE-01 closed).
  - **Volt/VAR**: recommend; rate-limit => blocked (OC-4 high-risk); auto => EXECUTED on MG001.
- The validation **caught a real engine bug**: the auto approver used the requester's
  identity and was correctly blocked by the two-person rule — fixed with a distinct
  `automation:supervisor` approver (P4-2).
- Controller verified: polls `/automation/tick`, heartbeat healthy, inert with the flag off.
- Portal typecheck clean; screenshot in [`docs/oms-automation/`](docs/oms-automation/).

## Enabling (operators) — layered

1. `OC_AUTOMATION_ENABLED=true` (engine evaluates; recommend-only — governed proposals,
   no actuation).
2. `PATCH /automation/policies/{id}` `enabled=true` (review bounds).
3. To actuate: that policy `mode=auto` **and** `OC_CONTROLS_ENABLED=true`. Run
   recommend first.

## Deployment / migration

- Apply `sql/020_automation.sql` (idempotent; wired into `init-db.sh`).
- Optionally run the controller:
  `docker compose -f docker-compose.yml -f docker-compose-automation.yml up -d automation-controller`.
- No change to existing services; both flags absent ⇒ safe (engine + actuation OFF).

Design reference: [`OPERATIONAL_CONTROLS.md`](OPERATIONAL_CONTROLS.md) (Phase 4 section).
Commits are preserved **un-squashed and un-rebased** (P4-1 → P4-4).
