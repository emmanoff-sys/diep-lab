# Release 2 Risk Register
### Planning Baseline v1.2 | Updated: 2026-07-06

| Revision | Date | Change |
|----------|------|--------|
| 1.0 | 2026-07-05 | Initial Release 2 risk register |
| 1.1 | 2026-07-05 | HOLD remediation: carries forward unresolved Release 1 risks and aligns ownership/mitigations to Sprint 0 and Entry Gate control |
| 1.2 | 2026-07-06 | Release 2 validation framework executed for R2-RISK-017; evidence failed release gate, so the risk remains mitigated but not resolved |
| 1.3 | 2026-07-06 | R2-PLAT-008 final evidence rerun completed; security and legacy platform profiles passed, but unit/service/database/Docker profiles remain non-green, so R2-RISK-017 remains mitigated and HOLD remains in force |

> Probability scale: 1 = Rare, 2 = Unlikely, 3 = Possible, 4 = Likely, 5 = Almost Certain
> Impact scale: 1 = Negligible, 2 = Minor, 3 = Moderate, 4 = Major, 5 = Critical
> Risk Score = Probability x Impact | HIGH >= 12 | MEDIUM 6-11 | LOW 1-5

## Release 1 Risk Carry-Forward Map

| Release 1 Risk | Release 2 Disposition |
|---------------|-----------------------|
| RISK-001 - Directory Structure Drift | carried as R2-RISK-014 |
| RISK-002 - DLMS/COSEM Test Environment Gap | carried as R2-RISK-003 |
| RISK-003 - Sibling Branch Divergence | carried as R2-RISK-011 |
| RISK-004 - Host VM Instability | carried as R2-RISK-012 |
| RISK-005 - AI Engineering Agent Scope Creep | carried as R2-RISK-013 |
| RISK-006 - IAM Design Underspecification | carried as R2-RISK-015 |
| RISK-007 - Key Person Dependency on Single Architect | carried as R2-RISK-009 |
| RISK-008 - External ADMS API Contract Volatility | carried as R2-RISK-016 |

## Open Risks

### R2-RISK-001 - Entry Gate Slippage from Specification Debt

| Field | Value |
|-------|-------|
| Category | Governance / Scope |
| Description | Release 2 implementation could be authorized before the WP-005-05..14 specification package is approved, recreating the same scope ambiguity the Release 1 freeze was intended to stop. |
| Probability | 3 |
| Impact | 4 |
| Risk Score | 12 (HIGH) |
| Owner | PMO Lead / Enterprise Architect |
| Mitigation | Treat specification approval as a non-negotiable entry gate. No Sprint 1 commitment until the spec package is signed off. |
| Contingency | Rebaseline Release 2 to planning-only and defer execution start. |

### R2-RISK-002 - EPIC-003 Review Backlog Becomes Release 2 Design Debt

| Field | Value |
|-------|-------|
| Category | Architecture |
| Description | AR-020 through AR-033 remain open against the framework and platform foundation. If Release 2 services become load-bearing before this backlog is addressed, latent design issues may surface inside metering work. |
| Probability | 4 |
| Impact | 4 |
| Risk Score | 16 (HIGH) |
| Owner | Enterprise Architect |
| Mitigation | Approve a dated AR backlog closure plan during Sprint 0 and clear the highest-risk reviews before Sprint 2. |
| Contingency | Freeze downstream service contract changes until affected reviews are closed. |

### R2-RISK-003 - DLMS/COSEM Test Harness Not Ready

| Field | Value |
|-------|-------|
| Category | Technical / Environment |
| Carry-forward From | RISK-002 |
| Description | The known DLMS/COSEM test-environment gap blocks trustworthy validation of EPIC-007 and everything downstream. |
| Probability | 4 |
| Impact | 4 |
| Risk Score | 16 (HIGH) |
| Owner | DevSecOps Lead / Backend Tech Lead |
| Mitigation | Close RISK-002 from the EECR through R2-EN-02 and ADR-R2-04 before the Entry Gate can record a pass decision. |
| Contingency | Keep EPIC-007 out of implementation scope; do not allow APPROVED status without end-to-end test execution. |

### R2-RISK-004 - Meter-to-Topology Identity Model Remains Ambiguous

| Field | Value |
|-------|-------|
| Category | Data / Architecture |
| Description | If meter identity, asset identity, and topology-version linkage are not frozen early, EPIC-008 through EPIC-010 will encode incompatible assumptions. |
| Probability | 4 |
| Impact | 5 |
| Risk Score | 20 (HIGH) |
| Owner | Enterprise Architect / Backend Tech Lead |
| Mitigation | Freeze the identity model in EPIC-006 through ADR-R2-02 and require architecture approval before ingestion schemas are committed. |
| Contingency | Introduce a compatibility mapping layer and absorb the rework into a controlled ADR-backed change. |

### R2-RISK-005 - Metering Data Volume Exceeds Initial Persistence Model

| Field | Value |
|-------|-------|
| Category | Performance / Data |
| Description | Raw reads, interval data, and event growth may exceed naive Postgres/Timescale design choices, leading to retention, partitioning, or query-performance issues late in the release. |
| Probability | 3 |
| Impact | 4 |
| Risk Score | 12 (HIGH) |
| Owner | DBA / Data Platform Lead |
| Mitigation | Define raw, normalized, and retention tiers in the architecture evolution plan and prove them with performance tests before EPIC-010 closes. |
| Contingency | Reduce data granularity in non-critical paths and replan long-retention analytics into later releases. |

### R2-RISK-006 - Tenant Isolation Regression in Metering APIs

| Field | Value |
|-------|-------|
| Category | Security |
| Description | Metering data introduces high-volume multi-tenant queries. Any lapse in tenant scoping or RBAC reuse would create data leakage risk. |
| Probability | 3 |
| Impact | 5 |
| Risk Score | 15 (HIGH) |
| Owner | Security Lead / Backend Tech Lead |
| Mitigation | Reuse `reos-common` tenant scoping patterns, require security review on query paths, and add explicit cross-tenant integration tests. |
| Contingency | Block release, revert exposed endpoints, and raise an incident-level security response. |

### R2-RISK-007 - External Meter or Head-End Contract Variability

| Field | Value |
|-------|-------|
| Category | External Dependency |
| Description | Real meter fleets and head-end integrations may vary by vendor, firmware, and object model, creating contract churn if the driver abstraction is too narrow. |
| Probability | 3 |
| Impact | 3 |
| Risk Score | 9 (MEDIUM) |
| Owner | DLMS/COSEM SME / Backend Tech Lead |
| Mitigation | Define an anti-corruption layer and explicit protocol capability model in EPIC-007. |
| Contingency | Limit Release 2 to the approved vendor/profile subset and schedule broader compatibility as follow-on scope. |

### R2-RISK-008 - Deployment Readiness Debt Delays Integrated Validation

| Field | Value |
|-------|-------|
| Category | Operational |
| Description | TD-11, TD-12, TD-13, and AR-052 staging conditions may delay the first integrated validation even if feature work progresses on schedule. |
| Probability | 4 |
| Impact | 5 |
| Risk Score | 20 (HIGH) |
| Owner | Release Manager / DevSecOps Lead / SRE Lead |
| Mitigation | Treat deployment readiness as a parallel Sprint 0 through Sprint 3 workstream, beginning with R2-OPS-01 and Entry Gate approval of the staging-readiness plan. |
| Contingency | Hold Release 2 at engineering-complete status and do not make deployment claims. |

### R2-RISK-009 - Key Person Dependency on Architect and Domain SMEs

| Field | Value |
|-------|-------|
| Category | People / Delivery |
| Carry-forward From | RISK-007 |
| Description | EPIC-006 through EPIC-010 rely on a small number of architecture and domain reviewers. Approval and design decisions may bottleneck. |
| Probability | 3 |
| Impact | 4 |
| Risk Score | 12 (HIGH) |
| Owner | PMO Lead / Engineering Manager |
| Mitigation | Assign named backup reviewers and secure part-time SME allocation during Sprint 0, before the Entry Gate pass decision. |
| Contingency | Escalate to steering committee for temporary delegated authority. |

### R2-RISK-010 - TD-14 Distracts the Release 2 Critical Path

| Field | Value |
|-------|-------|
| Category | Delivery / Technical Debt |
| Description | The repository-wide Ruff baseline (TD-14) may attract cleanup effort during Release 2 even though it is outside the current RE-OS delivery boundary. |
| Probability | 2 |
| Impact | 2 |
| Risk Score | 4 (LOW) |
| Owner | Platform Lead |
| Mitigation | Keep TD-14 explicitly out of Sprint 1 and off the release critical path unless R2 scope enters those legacy modules. |
| Contingency | Spin TD-14 into a separate modernization WP with independent approval and capacity. |

### R2-RISK-011 - Topology Branch Divergence

| Field | Value |
|-------|-------|
| Category | Technical / Integration |
| Carry-forward From | RISK-003 |
| Description | `feature/adms-topology-import` and `feature/dlms-driver` contain non-overlapping live behavior. Rebuilding topology features from only one source can silently regress version-history behavior. |
| Probability | 3 |
| Impact | 4 |
| Risk Score | 12 (HIGH) |
| Owner | Backend Tech Lead |
| Mitigation | Before WP-006-05 or WP-006-07 begins, diff both branches bidirectionally, produce a reconciliation plan, and require Enterprise Architect sign-off on the merge strategy. |
| Contingency | Keep both branches read-only until a formal reconciliation workstream is approved. |

### R2-RISK-012 - Host VM Stability

| Field | Value |
|-------|-------|
| Category | Infrastructure / Reliability |
| Carry-forward From | RISK-004 |
| Description | The lab VM has a history of write-acknowledged-not-persisted corruption affecting Kafka, Redis, and TimescaleDB. That root cause remains relevant to Release 2 validation readiness. |
| Probability | 2 |
| Impact | 5 |
| Risk Score | 10 (MEDIUM) |
| Owner | Infra Tech Lead / SRE Lead |
| Mitigation | Carry host-stability monitoring and backup/restore verification into Sprint 0 staging-readiness planning and before any integrated validation. |
| Contingency | Use restore and failover runbooks; do not treat staging evidence as durable until substrate checks are complete. |

### R2-RISK-013 - AI Engineering Scope Creep

| Field | Value |
|-------|-------|
| Category | Governance |
| Carry-forward From | RISK-005 |
| Description | AI engineering agents may implement beyond Work Package scope or modify governed artefacts without explicit authority. |
| Probability | 3 |
| Impact | 3 |
| Risk Score | 9 (MEDIUM) |
| Owner | PMO Lead / Enterprise Architect |
| Mitigation | Maintain GOV-002 controls, require human approval for all merges, and keep Sprint 0 / Sprint 1 scope boundaries explicit in package documents. |
| Contingency | Reject out-of-scope changes and restart against the correct Work Package package. |

### R2-RISK-014 - Directory Structure Drift

| Field | Value |
|-------|-------|
| Category | Architecture / Repository Governance |
| Carry-forward From | RISK-001 |
| Description | Future Release 2 work may introduce repository paths outside the LLD-approved monorepo structure without corresponding architecture governance. |
| Probability | 3 |
| Impact | 3 |
| Risk Score | 9 (MEDIUM) |
| Owner | Platform Lead / Enterprise Architect |
| Mitigation | Keep directory additions under architecture review and ensure Sprint 1 Work Package packages cite the approved repository boundary. |
| Contingency | Raise an ECR for any justified structural addition before implementation proceeds. |

### R2-RISK-015 - RBAC Taxonomy Dependency from Release 1

| Field | Value |
|-------|-------|
| Category | Security / Architecture |
| Carry-forward From | RISK-006 |
| Description | The Release 1 RBAC and permission taxonomy remains a dependency for metering APIs. If role/permission semantics remain ambiguous, Release 2 query and control paths may require rework. |
| Probability | 3 |
| Impact | 4 |
| Risk Score | 12 (HIGH) |
| Owner | Enterprise Architect / Security Lead |
| Mitigation | Tie metering authorization design to the approved Release 1 role taxonomy and keep AR-033 closure planning in Sprint 0. |
| Contingency | Restrict early Release 2 authorization to conservative roles until taxonomy closure is complete. |

### R2-RISK-016 - ADMS API Contract Volatility

| Field | Value |
|-------|-------|
| Category | External Dependency |
| Carry-forward From | RISK-008 |
| Description | ADMS integration scope in EPIC-006 may be forced to change if vendor contract or authentication behavior shifts before WP-006-07. |
| Probability | 3 |
| Impact | 3 |
| Risk Score | 9 (MEDIUM) |
| Owner | Backend Tech Lead / Architect / ADMS SME |
| Mitigation | Maintain an anti-corruption layer and confirm the pinned ADMS contract before WP-006-07 enters implementation. |
| Contingency | Contain adaptation in a dedicated follow-on work package rather than spreading vendor assumptions across EPIC-006. |

### R2-RISK-017 - Sprint 1 Downstream Quality Gate Environment Gap

| Field | Value |
|-------|-------|
| Category | Test / Environment / Delivery |
| Carry-forward From | Sprint 1 execution |
| Description | The authorized WP-006 slice passes targeted tests and service-ci gates, and the Platform Recovery Programme has removed several validation ambiguities. Broader Release 2 validation is still not green because unit/service/database/Docker profiles have objective failures or missing operational substrate evidence. |
| Probability | 4 |
| Impact | 4 |
| Risk Score | 16 (HIGH) |
| Owner | QA Lead / DevSecOps Lead / Platform Lead |
| Mitigation | R2-PLAT-001 through R2-PLAT-008 completed. Classification, legacy hostname audit, security validation, and legacy platform validation are green. Remaining non-green evidence is specific: unit profile failures, service integration failures/errors, database service unavailability, and Docker daemon unavailability. |
| Contingency | Hold WP-006-03B and later work until unit, service integration, database, Docker, and release-gate evidence is green in `release2-validation.yml` or an equivalent governed run, or the Programme Board formally accepts residual risk. |

## Executive Risk View

Top Release 2 risks are:

1. R2-RISK-004 - meter/topology identity ambiguity
2. R2-RISK-008 - deployment-readiness debt
3. R2-RISK-002 / R2-RISK-003 - review backlog and DLMS harness readiness
4. R2-RISK-006 / R2-RISK-015 - security and RBAC dependency risk
5. R2-RISK-017 - downstream quality gate environment gap
6. R2-RISK-011 - topology branch divergence

## Sprint 0 Closure Risk Position

| Risk | Sprint 0 Status | Entry Gate Position |
|------|-----------------|---------------------|
| R2-RISK-001 | CONTROLLED | spec trace accepted for Sprint 1 topology scope |
| R2-RISK-002 | CONTROLLED WITH CONDITION | AR backlog closure plan active; not a Sprint 1 topology blocker |
| R2-RISK-003 | CONTROLLED WITH CONDITION | DLMS selftest PASS; real-meter/reference-stack validation required before EPIC-007 closure |
| R2-RISK-004 | CONTROLLED | ADR-R2-02 approved in principle; WP-006-01 must prove schema lineage |
| R2-RISK-006 | CONTROLLED | tenant/RBAC/audit controls carried forward |
| R2-RISK-008 | CONTROLLED WITH CONDITION | no staging/deployment claim in Sprint 1; TD path remains downstream gate |
| R2-RISK-009 | CONTROLLED | review roles recorded; monitor availability |
| R2-RISK-011 | CONTROLLED WITH CONDITION | branch reconciliation remains required before WP-006-05/WP-006-07 load-bearing merge work |
| R2-RISK-012 | CONTROLLED WITH CONDITION | environment evidence classified; staging substrate remains downstream gate |
| R2-RISK-015 | CONTROLLED | conservative RBAC dependency accepted for topology Sprint 1 |

Recommendation: Sprint 1 may start under `GO WITH CONDITIONS` and the conditions in
`RELEASE-2-ENTRY-GATE-EVIDENCE.md`.

## Sprint 1 Interim Risk Position

| Risk | Sprint 1 Status | Next Authorization Position |
|------|-----------------|-----------------------------|
| R2-RISK-004 | CONTROLLED | WP-006-01 schema lineage evidence produced |
| R2-RISK-011 | CONTROLLED WITH CONDITION | no branch-reconciliation-dependent work authorized |
| R2-RISK-016 | CONTROLLED WITH CONDITION | ADMS contract remains future-scope |
| R2-RISK-017 | MITIGATED / R2-PLAT-008 RELEASE GATE FAILED | HOLD next work package until unit, service integration, database, Docker, and release-gate evidence is green and governance approves closure or formally accepts residual risk |

Recommendation: do not authorize WP-006-03B, WP-006-04, EPIC-007, or later work until R2-RISK-017
is closed or formally accepted by governance.
