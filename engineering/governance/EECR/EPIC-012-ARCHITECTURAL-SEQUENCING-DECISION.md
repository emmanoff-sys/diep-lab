# EPIC-012 Architectural Sequencing Decision

## Programme Decision Record

| Field | Value |
| --- | --- |
| Document ID | EPIC-012-ARCHITECTURAL-SEQUENCING-DECISION |
| Programme | RE-OS / DAEP |
| Decision Date | 2026-07-10 |
| Decision Authority | Programme Lead (Emmanuel Offiong) |
| Strategic Basis | PAR-002 Phase 2 Architecture & Deployment Readiness Review (RISK-PAR002-03) |
| Next Programme Phase | PAO-028 — EPIC-012: Advanced Grid Analytics |
| EECR Reference | EECR-CHG-127 |

---

## Decision

EPIC-012 Advanced Grid Analytics shall begin with an **architectural enablement
work package**, not an analytics feature work package.

The first work package of EPIC-012 shall be scoped as an architectural
refactoring and enablement deliverable, with the following objectives:

### Mandatory First Work Package Scope

1. **Refactor legacy P5 analytics** currently located under `fastapi/dms/`
   into a dedicated `services/` package consistent with the rest of the platform
   architecture.

2. **Define a reusable analytics service layer and interfaces** — package
   boundary, public API, canonical input and output contracts.

3. **Establish common contracts** for analytical inputs (network topology,
   operational state, metering events) and outputs (estimates, recommendations,
   alerts, audit records).

4. **Ensure the new analytics layer consumes existing services** — specifically:
   - `adms_topology_import` / topology services (WP-007) for network model
   - `adms_network_state` (WP-008) for operational state
   - `adms_operations` / decision support (WP-009) for switching and OMS context
   - `adms_operational_intelligence` (WP-010) for advisory and intelligence baseline
   - Connector layer (EPIC-011 WP-011-01..04) for live field measurements

   The analytics layer shall not bypass, re-implement, or duplicate any of these
   services.

5. **Preserve deterministic behaviour and full regression compatibility** — all
   existing P5 tests must pass at the new module path. No P5 analytical function
   shall be silently dropped or degraded during the migration.

### Prohibited in First Work Package

- Introducing new analytical functions (state estimation, power flow, Volt/VAR,
  contingency optimisation) before the architectural foundation is validated.
- Extending or modifying `fastapi/dms/` as the intended home for analytics.
- Bypassing the `services/` architecture for performance or convenience.

---

## Rationale

This sequencing follows the discipline demonstrated throughout the programme:

- **WP-006..010** established the ADMS foundation before operator applications.
- **WP-013-01** established operational readiness before WP-013-02 capability.
- **WP-011-01** established canonical contracts before any connector implementation.
- **WP-026** (PAO-026) resolves reliability and observability gaps before
  production rollout.

EPIC-012 shall follow the same pattern: architectural foundation before
analytical capability.

PAR-002 identified `fastapi/dms/` as RISK-PAR002-03 — a pre-Phase-2 path that
predates the `services/` architecture restructuring. Extending P5 analytics from
that location without first re-architecturing the layer would:
- create a two-tier analytics architecture (some analytics in `services/`,
  some in `fastapi/dms/`);
- make cross-analytics dependencies harder to manage;
- increase the cost of later migration as more analytics build on the legacy path.

---

## Subsequent Work Packages (Post-Foundation)

Only after the architectural enablement work package is complete and merged may
the programme introduce new analytical capabilities. The intended sequence is:

| Priority | Capability | Notes |
| --- | --- | --- |
| 1 (Foundation) | P5 re-architecture + service layer | Required gate for all subsequent WPs |
| 2 | State estimation | Consumes topology + operational state + metering |
| 3 | Power flow | Consumes topology + state estimation output |
| 4 | Volt/VAR optimisation | Consumes power flow + operational state |
| 5 | Contingency optimisation | Consumes power flow + switching operations |
| 6 | Advanced network analytics | Load forecasting, DER modelling, etc. |

Exact WP boundaries and authorisation orders for items 2 through 6 are subject
to separately governed PAOs and are not authorised by this decision record.

---

## Relationship to RISK-PAR002-03

This decision formally establishes the resolution path for RISK-PAR002-03 (P5
Analytics Legacy Path Promotion Risk) as recorded in the risk register:

> Mitigation: EPIC-012 WP scope documentation must explicitly include
> re-architecturing P5 analytics from `fastapi/dms/` to a new
> `services/adms_grid_analytics/` (or equivalent) package, with integration
> into `adms_operational_intelligence`. The `fastapi/dms/` path must not be
> promoted or extended.

This decision record satisfies the mitigation requirement. RISK-PAR002-03 status
shall be updated to CONTROLLED once this document is baseline-integrated.

---

## Effect

No engineering is authorised by this decision. Engineering and PAO issuance
for EPIC-012 remain separate programme actions.

This decision record constrains the scope of PAO-028 when it is issued: the
first EPIC-012 work package authorised by PAO-028 shall be the architectural
enablement work package described above, not an analytics feature work package.
