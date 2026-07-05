# WP-005-04 Release Closure Report
### Audit Service — Immutable Platform Audit Log | PCS-001 | 2026-07-05

## Executive Summary

WP-005-04 is closed for the currently authorised engineering baseline. The Audit Service implementation was human approved and merged through PR #17 into `develop/v1.1` at `946451222eaef3c988f80963e5eddce24ec7720e`. The release tag `wp-005-04-audit-service-v1.0` points at the merge commit. All required CI and CodeQL checks are green.

## Objectives

| Objective | Result |
|-----------|--------|
| Deliver immutable platform audit service | Achieved |
| Integrate identity-service audit event production | Achieved |
| Preserve governance and GOV-002 approval controls | Achieved |
| Close pre-merge AR-052 conditions | Achieved |
| Freeze baseline after merge | Achieved |

## Delivered Functionality

- `audit-service` FastAPI microservice with write, query, single-event retrieval, and hash-chain verification endpoints.
- TimescaleDB audit schema with immutable trigger, retention/compression policy, and `chain_state`.
- Per-actor SHA-256 hash-chain service.
- Kafka consumer for `iam.audit.events` and `user.registered`, plus DLQ handling.
- Identity-service audit event emission across auth, MFA, RBAC, and user administration paths.
- JWKS/RS256 validation, `admin:audit` read gate, and internal-service write token split.

## Architecture Summary

AR-052 scored the implementation at 90/100 and closed as APPROVED / MERGED / BASELINE FROZEN after pre-merge conditions were resolved. The service follows the approved identity-service microservice pattern and the LLD v2.0 §7.6 audit-service architecture.

## Security Summary

Security gates passed: Bandit, CodeQL, pip-audit, Trivy CRITICAL/HIGH, and Secrets. Sensitive logging findings were remediated before merge. PII handling is documented; PII is excluded from structured logs while remaining available to authorised `admin:audit` query paths.

## CI/CD Summary

GitHub Actions run `28740300083` passed Stage 1, Stage 2, Stage 3, Secrets, Stage 4, and Stages 5/6/7. Separate CodeQL check `85221840383` passed. Stage 7 registry push remains deployment-ref and credential gated.

## Testing Summary

Unit and component tests passed under Stage 4. Coverage gate passed after source paths were corrected to the actual monorepo service/library locations.

## Governance Summary

AR-052 and EECR-CHG-067 through EECR-CHG-073 are closed. EECR-CHG-074 records PCS-001 closure. WP-005-04 status is IMPLEMENTED / MERGED / BASELINE FROZEN.

## Technical Debt

The following remain open before first staging deployment:

- C-AR052-02: populate or remove `audit_kafka_consumer_lag`.
- C-AR052-03: add same-actor REST hash-chain serialisation guard.
- C-AR052-05: confirm port 8004.
- C-AR052-06: confirm `chain_state` UPDATE permission.
- Registry credentials, staging VMs, DAST baseline, and rollback drill remain release-readiness items outside WP-005-04 merge scope.

## Lessons Learned

- CI gates must be scoped to the approved RE-OS boundary in a monorepo.
- Internal packages need explicit CI bootstrap or registry availability.
- CodeQL findings should be treated as source-of-truth security feedback, not bypassed.
- Registry push should be tied to deployment refs and configured credentials.

## Recommendations

Close the release-planning/governance loop before authorising additional implementation. Resolve staging prerequisites and prioritise the AR-052 carry-forward items before any deployment exercise.

