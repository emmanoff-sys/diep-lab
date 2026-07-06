# ADR-R2-07 - Release 2 Validation Governance Framework
### DAEP / RE-OS | Architecture Decision Record | Revision 1.0 | 2026-07-06

## Status

Proposed for approval.

## Context

R2-RISK-017 identified that Release 2 topology/CIM work intersects legacy platform modules that are
not fully covered by the Release 1 service-ci workflow. The risk is not application code. It is a
release-engineering and validation-governance gap.

## Decision

Release 2 will use a dedicated validation framework and additive GitHub Actions workflow to govern:

- unit tests,
- service integration tests,
- database integration tests,
- Docker validation,
- security validation,
- legacy platform validation,
- release gate validation.

Every existing test file must be classified in `RELEASE-2-TEST-CLASSIFICATION.csv`. R2-RISK-017
closure requires the binary criteria in `RELEASE-2-R2-RISK-017-CLOSURE-CRITERIA.md`.

## Alternatives Considered

| Alternative | Decision |
|-------------|----------|
| Continue using targeted WP evidence only | Rejected; does not close downstream validation ambiguity |
| Fold legacy tests into Release 1 service-ci | Rejected; would change the frozen Release 1 validation boundary |
| Create a separate Release 2 validation workflow | Accepted; additive, auditable, and scope-contained |

## Consequences

Positive:

- R2-RISK-017 becomes auditable through named profiles and binary criteria.
- Later WP authorization has objective evidence.
- Release 1 frozen workflows remain intact.

Negative:

- Additional CI runtime and workflow maintenance.
- Human governance approval is still required before WP-006-03B can unlock.

## Governance

Approval required from:

- Enterprise Architect,
- DevSecOps Lead,
- QA Lead,
- Release Manager,
- Programme Board.
