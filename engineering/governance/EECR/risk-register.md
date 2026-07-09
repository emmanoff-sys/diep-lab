# Risk Register — DAEP / RE-OS Program
### EECR v1.0 | Updated: 2026-07-01

> **Probability scale:** 1 = Rare, 2 = Unlikely, 3 = Possible, 4 = Likely, 5 = Almost Certain
> **Impact scale:** 1 = Negligible, 2 = Minor, 3 = Moderate, 4 = Major, 5 = Critical
> **Risk Score** = Probability × Impact | **HIGH** ≥ 12 | **MEDIUM** 6–11 | **LOW** 1–5

---

## Open Risks

### RISK-001 — Directory Structure Drift from LLD v2.0 §3.1

| Field | Value |
|-------|-------|
| Risk ID | RISK-001 |
| Category | Architecture |
| Description | Future Work Packages may add ad hoc top-level directories to the RE-OS monorepo without updating the LLD reference, causing the physical layout to diverge from the architectural specification. |
| Affected WPs | WP-001-04 (mitigation), all future WPs |
| Probability | 3 (Possible) |
| Impact | 3 (Moderate — complicates onboarding, breaks structure-lint CI) |
| **Risk Score** | **9 (MEDIUM)** |
| Owner | Platform Lead |
| Mitigation | WP-001-04 adds a CI structure-lint check that fails the build if any unregistered top-level directory is introduced. Until WP-001-04 is merged, directory additions require explicit architecture review sign-off. |
| Contingency | Retroactively audit and relocate misplaced directories; raise an ECR to update LLD if the addition is architecturally justified. |
| Status | OPEN — mitigation in progress (WP-001-04 not yet started) |
| Target Resolution | 2026-07-28 (M1 gate) |
| Linked WPs | WP-001-04 |

---

### RISK-002 — DLMS/COSEM Test Environment Gap

| Field | Value |
|-------|-------|
| Risk ID | RISK-002 |
| Category | Technical / Environment |
| Description | The current engineering environment lacks a Python runtime with pytest installed, making DLMS driver tests unverifiable in the local shell. This blocks validation of R2's EPIC-007 (DLMS/COSEM Protocol Driver). |
| Affected WPs | WP-003-01 (FastAPI template must account for test requirements), EPIC-007 (R2) |
| Probability | 4 (Likely — environment not yet remediated) |
| Impact | 4 (Major — blocks R2 DLMS Epic; could delay metering capability) |
| **Risk Score** | **16 (HIGH)** |
| Owner | DevSecOps Lead |
| Mitigation | Establish a Docker-based test environment in WP-002-01 that includes Python 3.11+ with pytest, hypothesis, and all test dependencies. Add pytest to the R1 CI pipeline (WP-004-02). |
| Contingency | Use GitHub Actions runners for all test execution; block DLMS WPs from APPROVED status until test environment is verified end-to-end. |
| Status | OPEN — mitigation depends on WP-002-01 and WP-004-02 |
| Target Resolution | 2026-08-25 (M4 gate) |
| Linked WPs | WP-002-01, WP-004-02, EPIC-007 |

---

### RISK-003 — Sibling Branch Divergence (adms-topology-import / dlms-driver)

| Field | Value |
|-------|-------|
| Risk ID | RISK-003 |
| Category | Technical / Integration |
| Description | Two feature branches (`feature/adms-topology-import` and `feature/dlms-driver`) exist in the production stack and are not supersets of each other. The `feature/adms-topology-import` branch regressed the `/topology/versions` endpoint that exists on `feature/dlms-driver`. Recreating from one source can silently delete unique live features of the other. |
| Affected WPs | WP-006-07 (ADMS Topology Import Integration), WP-006-05 (Topology Version History API) |
| Probability | 3 (Possible — branches must be reconciled before merge) |
| Impact | 4 (Major — feature regression in production; `/topology/versions` lost) |
| **Risk Score** | **12 (HIGH)** |
| Owner | Backend Tech Lead |
| Mitigation | **Completed for WP-006-07 Objective 1 by AR-057 / EECR-CHG-101.** `feature/dlms-driver` is absorbed into `develop/v1.1`; `feature/adms-topology-import` is stale and lacks the approved topology version-history routes. Required strategy: start WP-006-07 implementation from current `develop/v1.1`; never merge `feature/adms-topology-import` wholesale; any branch delta must be explicitly listed, reviewed, and validated before import. |
| Contingency | If a future implementation attempts to use `feature/adms-topology-import` as a base, stop and raise an EDR/ECR before any merge. |
| Status | CONTROLLED — branch reconciliation complete; no-wholesale-merge strategy ratified by AR-057 / EECR-CHG-101 |
| Target Resolution | Before WP-006-04 begins (Sprint S8) |
| Linked WPs | WP-006-05, WP-006-07 |

---

### RISK-004 — Host VM Instability (Write-Acknowledged-Not-Persisted Corruption)

| Field | Value |
|-------|-------|
| Risk ID | RISK-004 |
| Category | Infrastructure / Reliability |
| Description | Recurring host-level corruption events (write-acknowledged-not-persisted) affecting Kafka, Redis, and TimescaleDB on the lab VM. The zero-backup gap was previously identified and is now closed, but the host-level root cause has not been confirmed as fully remediated. |
| Affected WPs | WP-002-02 (PostgreSQL/TimescaleDB), WP-002-03 (Redis), EPIC-002 broadly |
| Probability | 2 (Unlikely — backup gap closed; active monitoring in place) |
| Impact | 5 (Critical — data loss, service unavailability, potential replay integrity failure) |
| **Risk Score** | **10 (MEDIUM)** |
| Owner | Infra Tech Lead / SRE Lead |
| Mitigation | (1) Implement storage checksumming in WP-002-02; (2) add storage health metrics to WP-002-05 (Prometheus); (3) configure TimescaleDB continuous aggregates with checksums; (4) verify backup/restore round-trip before each environment promotion. |
| Contingency | Automated backup every 15 minutes; runbook for restoration from last known good snapshot; VM hypervisor failover procedure documented before M2. |
| Status | MONITORING — backup gap closed; host root cause unconfirmed |
| Target Resolution | 2026-08-11 (M2 gate) |
| Linked WPs | WP-002-02, WP-002-03, WP-002-05 |

---

### RISK-005 — AI Engineering Agent Scope Creep

| Field | Value |
|-------|-------|
| Risk ID | RISK-005 |
| Category | Governance |
| Description | AI engineering agents (Claude, ChatGPT, Codex) may implement features beyond the specified Work Package scope, introduce unreviewed abstractions, or modify architecture baseline documents without authorization. |
| Affected WPs | All WPs where AI agents are assigned |
| Probability | 3 (Possible) |
| Impact | 3 (Moderate — architectural drift; increased review burden) |
| **Risk Score** | **9 (MEDIUM)** |
| Owner | PMO Lead / Enterprise Architect |
| Mitigation | EECR AI Agent Operating Instructions (README §8) mandate scope boundaries. All AI-produced code requires human architecture review before APPROVED status. CI linting enforces file-path boundaries per WP scope. |
| Contingency | Reject PR if scope exceeds WP definition; require the agent session to be restarted against the correct WP Engineering Package. |
| Status | MITIGATED — controls in place |
| Target Resolution | Ongoing |
| Linked WPs | All |

---

### RISK-006 — IAM Design Underspecification

| Field | Value |
|-------|-------|
| Risk ID | RISK-006 |
| Category | Architecture |
| Description | The RBAC model (WP-005-02) spans multiple roles across field engineers, customers, installers, operators, and system administrators. If the role taxonomy is not fully specified in SRS/LLD before implementation begins, the data model may require breaking migrations in later releases. |
| Affected WPs | WP-005-01, WP-005-02, and all future services that consume RBAC |
| Probability | 3 (Possible) |
| Impact | 4 (Major — breaking schema change mid-program is expensive) |
| **Risk Score** | **12 (HIGH — elevated)** |
| Owner | Enterprise Architect |
| Mitigation | Architecture review for WP-005-02 must validate the complete role/permission taxonomy against all SRS user roles before the WP moves to IN PROGRESS. Raise ECR if LLD §7.2 does not provide sufficient detail. |
| Contingency | Design the permission table as a flat key-value permission store (not enum-constrained) to allow additive extension without breaking migrations. |
| Status | OPEN — architecture review for WP-005-02 not yet scheduled |
| Target Resolution | Before Sprint S6 begins |
| Linked WPs | WP-005-01, WP-005-02 |

---

### RISK-007 — Key Person Dependency on Single Architect

| Field | Value |
|-------|-------|
| Risk ID | RISK-007 |
| Category | People / Delivery |
| Description | All architecture reviews are currently assigned to a single Enterprise Architect. If that individual is unavailable, the architecture review gate becomes a bottleneck and WPs cannot advance to APPROVED status. |
| Affected WPs | All WPs requiring architecture review |
| Probability | 2 (Unlikely) |
| Impact | 4 (Major — blocks all WP approvals until resolved) |
| **Risk Score** | **8 (MEDIUM)** |
| Owner | Engineering Manager / PMO Lead |
| Mitigation | Identify and train a backup Architecture Reviewer by M2. Document Architecture Review Checklist so review can be performed by any appropriately senior engineer. |
| Contingency | Escalate to program steering committee to appoint a temporary reviewer. |
| Status | OPEN |
| Target Resolution | 2026-08-11 (M2 gate) |
| Linked WPs | All |

---

### RISK-008 — External ADMS API Contract Volatility

| Field | Value |
|-------|-------|
| Risk ID | RISK-008 |
| Category | External Dependency |
| Description | The ADMS (Advanced Distribution Management System) topology import integration (WP-006-07) depends on an external ADMS API contract. If the ADMS vendor changes the API schema or authentication model before or during WP-006-07 implementation, rework is required. |
| Affected WPs | WP-006-03 (CIM Parser), WP-006-07 (ADMS Integration) |
| Probability | 3 (Possible — vendor APIs evolve) |
| Impact | 3 (Moderate — rework cost; schedule delay) |
| **Risk Score** | **9 (MEDIUM)** |
| Owner | Backend Tech Lead / Architect |
| Mitigation | Implemented through the approved ADMS contract baseline, WP-006-07 anti-corruption/import foundation, and WP-006-08 production runtime validation. Compatibility and production integration tests now cover the pinned import contract and runtime behaviour. |
| Contingency | If the external ADMS supplier changes the contract after this baseline, scope a future WP-006-09 / EDR under Programme Board control rather than changing WP-006-07 or WP-006-08 retrospectively. |
| Status | CLOSED — resolved by approved ADMS contract baseline, WP-006-07 closure, and WP-006-08 engineering validation |
| Target Resolution | 2026-07-08 |
| Linked WPs | WP-006-03, WP-006-07 |

---

## Closed Risks

| Risk ID | Closure Date | Closure Evidence |
|---------|--------------|------------------|
| RISK-008 | 2026-07-08 | Approved ADMS contract baseline; WP-006-07 closure; WP-006-08 production runtime validation through OA-020; Release 2 classification alignment for WP-006-08 tests. |

---

## Risk Heat Map

```
Impact
  5 |                    |                    | R004               |
    |                    |                    |                    |
  4 |                    | R002               | R003, R006         |
    |                    |                    |                    |
  3 |                    | R001, R005, R008   |                    |
    |                    |                    |                    |
  2 |                    | R007               |                    |
    |                    |                    |                    |
  1 |                    |                    |                    |
    +--------------------+--------------------+--------------------
    Probability:         2 (Unlikely)         3 (Possible)         4 (Likely)

Key: HIGH (■), MEDIUM (□)
```

---

## Risk Register Change Log

| Date | Risk ID | Change | Author |
|------|---------|--------|--------|
| 2026-07-01 | RISK-001 through RISK-008 | Initial population from WP-001-01 delivery and program baseline review | PMO Lead |
| 2026-07-08 | RISK-008 | Closed after approved ADMS contract baseline, WP-006-07 closure, and WP-006-08 validation evidence | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-08 | WP-007 | PAO-008 release preparation identified no new open risk; production API exposure, deployment, and operational acceptance remain separately governed future activities | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-08 | WP-007 | Closed after GOV-002 PR #40 merge; topology services foundation integrated into `develop/v1.1` with no new open risk | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-008 | PAO-011 release preparation identified no new open risk; persistence, SCADA ingestion, state estimation, production wiring, deployment, and operational acceptance remain separately governed future activities. Merge-sequencing note: `feature/wp-009-operations-foundation` is stacked on the WP-008 baseline and must follow WP-008 through governance | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-008 | Closed after GOV-002 PR #41 merge; operational network state foundation integrated into `develop/v1.1` with no new open risk | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-009 | Release preparation identified no new open risk; the layer is advisory-only — automatic switching execution, FLISR, SCADA protocols, state estimation, production wiring, deployment, and operational acceptance remain separately governed future activities | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-009 | Closed after GOV-002 PR #42 merge; outage management and switching operations foundation integrated into `develop/v1.1` with no new open risk | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-010 | Release preparation identified no new open risk; the layer is advisory-only — automatic switching execution, FLISR automation, SCADA protocols, state estimation, machine-learning inference, power-flow optimisation, production wiring, deployment, and operational acceptance remain separately governed future activities | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-010 | Closed after GOV-002 PR #43 merge; analytical decision services foundation integrated into `develop/v1.1` with no new open risk | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-013-01 | PAO-015 release preparation identified no new open risk; the package is documentation and evidence only — live-stack rehearsal execution, production go-live approval, operator applications, and external integrations remain separately governed future activities | Programme Engineering Manager / Release Engineering Lead |
| 2026-07-09 | WP-013-01 | Closed after GOV-002 PR #44 merge; platform operational readiness layer integrated into `develop/v1.1` with no new open risk | Programme Engineering Manager / Release Engineering Lead |
