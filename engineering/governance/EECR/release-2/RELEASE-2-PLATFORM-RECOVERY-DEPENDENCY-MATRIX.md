# Release 2 Platform Recovery Dependency Matrix
### DAEP / RE-OS | R2-RISK-017 Recovery Dependencies | Revision 1.0 | 2026-07-06

## 1. Work Package Dependency Matrix

| Work Package | Depends On | Enables | Can Run In Parallel With |
|--------------|------------|---------|---------------------------|
| R2-PLAT-001 | Test classification manifest | R2-PLAT-006, R2-PLAT-008 | R2-PLAT-002, R2-PLAT-004, R2-PLAT-007 |
| R2-PLAT-002 | Environment contract, CI runner access | R2-PLAT-003, R2-PLAT-005, R2-PLAT-008 | R2-PLAT-001, R2-PLAT-004, R2-PLAT-007 |
| R2-PLAT-003 | R2-PLAT-002, audit-service settings contract | R2-PLAT-008 | R2-PLAT-004, R2-PLAT-006, R2-PLAT-007 |
| R2-PLAT-004 | CI runner access | R2-PLAT-008 | R2-PLAT-001, R2-PLAT-002, R2-PLAT-007 |
| R2-PLAT-005 | R2-PLAT-002, classification manifest | R2-PLAT-008 | R2-PLAT-006, R2-PLAT-007 |
| R2-PLAT-006 | R2-PLAT-001, dependency profile decision | R2-PLAT-008 | R2-PLAT-003, R2-PLAT-005, R2-PLAT-007 |
| R2-PLAT-007 | Dependency policy | R2-PLAT-008 | R2-PLAT-001, R2-PLAT-002, R2-PLAT-004, R2-PLAT-006 |
| R2-PLAT-008 | R2-PLAT-001 through R2-PLAT-007 complete or accepted | R2-RISK-017 closure decision; WP-006-03B authorization decision | None |

## 2. Validation Profile Coverage

| Profile | Required Recovery WPs |
|---------|------------------------|
| Unit Validation | R2-PLAT-001 |
| Service Integration Validation | R2-PLAT-001, R2-PLAT-003 |
| Database Integration Validation | R2-PLAT-002, R2-PLAT-003, R2-PLAT-005 |
| Docker Validation | R2-PLAT-004 |
| Security Validation | R2-PLAT-007 |
| Legacy Platform Validation | R2-PLAT-001, R2-PLAT-005, R2-PLAT-006 |
| Release Gate Validation | R2-PLAT-008 plus all upstream profile WPs |

## 3. Role Dependency Matrix

| Role | Primary WPs | Required Governance Interaction |
|------|-------------|---------------------------------|
| QA Lead | R2-PLAT-001, R2-PLAT-005 | Test classification and profile evidence approval |
| DevSecOps Lead | R2-PLAT-002, R2-PLAT-004, R2-PLAT-007 | CI runner, Docker, security evidence approval |
| DBA | R2-PLAT-002, R2-PLAT-003 | DB readiness, migration, and DSN evidence approval |
| Observability Lead | R2-PLAT-006 | Prometheus profile and residual-risk recommendation |
| Release Manager | R2-PLAT-008 | Evidence pack and authorization recommendation |
| Enterprise Architect | R2-PLAT-005, R2-PLAT-008 | Architecture impact and residual-risk disposition |
| PMO Lead | R2-PLAT-008 | GOV-002 scope and authorization control |

## 4. Critical Dependencies Before WP-006-03B

WP-006-03B authorization depends on R2-PLAT-008, which in turn depends on R2-PLAT-001 through
R2-PLAT-007. No partial completion is sufficient unless the Programme Board formally accepts the
remaining residual risk in writing.

