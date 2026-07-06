# Release 2 Platform Recovery Programme
### DAEP / RE-OS | Programme Recovery Board | Revision 1.0 | 2026-07-06

## 1. Authority and Scope

This programme responds to R2-RISK-017 after execution of the Release 2 Validation Framework.
Objective evidence shows the authorized implementation slice is healthy. The remaining failures are
Platform Engineering, validation governance, dependency-contract, and CI/CD execution failures.

This is not an EPIC-006 implementation programme. It does not authorize WP-006-03B, EPIC-007, or
any additional feature work.

## 2. Recovery Objective

Restore objective confidence in the Release 2 validation platform by remediating the failed
validation profiles until the Release 2 release gate can produce auditable green evidence or a
formally approved residual-risk acceptance.

## 3. Failed Validation Item Analysis

| Evidence Item | Failure | Root Cause Cluster | Recovery WP |
|---------------|---------|--------------------|-------------|
| Unit Validation | Pytest `ImportPathMismatchError` before test execution | Multi-package pytest import-root collision | R2-PLAT-001 |
| Service Integration Validation | Same pytest import-root collision | Multi-package pytest import-root collision | R2-PLAT-001 |
| Database Migration Bootstrap | `pg_isready` and `psql` unavailable locally | DB validation substrate incomplete | R2-PLAT-002 |
| Database Integration Validation | `DB_DSN` missing during audit-service collection | DB environment contract mismatch | R2-PLAT-003 |
| Docker Validation | Docker daemon unavailable | Runner/substrate not fit for Docker validation | R2-PLAT-004 |
| Legacy Platform Validation | `diep-timescaledb` unresolved from host | Legacy DB hostname assumes Docker network | R2-PLAT-005 |
| Legacy Platform Validation | Prometheus duplicate registry and optional-dependency assumptions | Observability dependency profile not deterministic | R2-PLAT-006 |
| Security Validation | pip-audit cannot resolve combined FastAPI pins | Dependency audit inputs combine incompatible product surfaces | R2-PLAT-007 |
| Release Gate Validation | Aggregation failed | Mandatory upstream profiles failed | R2-PLAT-008 |

## 4. Platform Recovery Roadmap

| Phase | Work Packages | Purpose | Exit Condition |
|-------|---------------|---------|----------------|
| Phase A - Validation Orchestration Stabilization | R2-PLAT-001 | Make classified test execution mechanically reliable | Unit and service integration profiles reach test execution without import-root collision |
| Phase B - Execution Substrate Readiness | R2-PLAT-002, R2-PLAT-004 | Provide governed DB and Docker execution capability | DB tooling/service evidence and Docker daemon/build evidence exist |
| Phase C - Environment Contract Closure | R2-PLAT-003, R2-PLAT-005 | Align service and legacy DB contracts with the Release 2 environment model | DB DSN and legacy DB hostname behavior are deterministic |
| Phase D - Dependency Determinism | R2-PLAT-006, R2-PLAT-007 | Remove optional-dependency ambiguity from validation and security audit | Prometheus profile and pip-audit surfaces produce binary evidence |
| Phase E - Release Gate Re-run and Governance Closure | R2-PLAT-008 | Produce final closure evidence for R2-RISK-017 | Release 2 validation gate PASS or residual risk formally accepted |

## 5. Recommended Execution Order

1. R2-PLAT-001 - Validation Profile Pytest Isolation
2. R2-PLAT-002 - Database Validation Substrate
3. R2-PLAT-003 - Database Environment Contract Alignment
4. R2-PLAT-004 - Docker Runner Readiness
5. R2-PLAT-005 - Legacy DB Hostname and Classification Recovery
6. R2-PLAT-006 - Legacy Observability Dependency Determinism
7. R2-PLAT-007 - Security Dependency Audit Segmentation
8. R2-PLAT-008 - Release Gate Evidence Re-run and Governance Closure

R2-PLAT-002 and R2-PLAT-004 may run in parallel if separate DevSecOps capacity is available.
R2-PLAT-006 and R2-PLAT-007 may also run in parallel after R2-PLAT-001 establishes stable
profile invocation.

## 6. Updated Programme Critical Path

| Critical Path Step | Status | Dependency | Impact |
|--------------------|--------|------------|--------|
| Sprint 1 authorized implementation slice | Complete | WP-006-01, WP-006-02, WP-006-03A | Implementation evidence remains usable |
| R2-RISK-017 validation framework | Complete | ADR-R2-07, validation profiles, classification | Risk mitigated but not resolved |
| Platform Recovery Programme | Required now | This document and recovery backlog | Blocks next authorization |
| Recovery WPs R2-PLAT-001 through R2-PLAT-008 | Not started | Programme Board approval | Required before release gate can pass |
| Release 2 Validation Gate re-run | Blocked | Recovery WPs complete | Required before R2-RISK-017 can resolve |
| WP-006-03B authorization | Locked | R2-RISK-017 resolved or accepted | Cannot proceed under current evidence |
| EPIC-007 authorization | Locked | R2-RISK-017 plus EPIC-007 harness controls | Cannot proceed under current evidence |

## 7. WP-006-03B Authorization Recommendation

WP-006-03B must remain locked until the following recovery work packages complete:

| Required Before WP-006-03B | Reason |
|----------------------------|--------|
| R2-PLAT-001 | WP-006-03B cannot be safely validated if the unit/service profiles fail before execution |
| R2-PLAT-002 | Database-backed topology/CIM validation needs governed DB substrate evidence |
| R2-PLAT-003 | Audit-service and DB-backed profiles must receive the environment variables required by their own contract |
| R2-PLAT-004 | Docker validation is a mandatory Release 2 profile and cannot be bypassed |
| R2-PLAT-005 | Legacy DB-dependent tests must not depend on ungoverned Docker-network names |
| R2-PLAT-006 | Legacy platform profile must be deterministic with or without Prometheus |
| R2-PLAT-007 | Security validation must produce actual CVE evidence rather than resolver failure |
| R2-PLAT-008 | Final release-gate aggregation must pass or have a formal residual-risk acceptance |

Recommendation: **do not authorize WP-006-03B until all eight recovery work packages are complete
or a Programme Board decision explicitly accepts remaining residual risk.**

## 8. Governance Recommendation

Recommendation: treat these activities as **supporting work packages under Release 2**, not as a
new dedicated Platform Engineering EPIC.

Justification:

- Governance: the failures are release-gate blockers for Release 2, not a new product capability
  stream. Creating a new EPIC would expand the programme taxonomy and could obscure the direct
  traceability to R2-RISK-017.
- Engineering risk: the work is cross-cutting but bounded to validation execution, CI substrate,
  environment contract, and audit evidence. It should remain tied to the Release 2 critical path.
- Long-term maintainability: the outputs should become durable Release 2 platform controls, but
  they are best recorded as recovery and enabling work packages now. A later programme may promote
  recurring platform hardening into a standing Platform Engineering EPIC if similar risks recur
  across multiple releases.

Decision posture: **supporting Release 2 recovery work packages, governed by R2-RISK-017 closure
criteria and Programme Board approval.**
