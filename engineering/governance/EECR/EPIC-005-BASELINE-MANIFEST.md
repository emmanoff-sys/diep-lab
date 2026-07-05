# EPIC-005 Baseline Manifest — PCS-001
### DAEP / RE-OS Programme | Frozen: 2026-07-05

## Baseline Identity

| Field | Value |
|-------|-------|
| Baseline Scope | EPIC-005 through WP-005-04 |
| Work Package | WP-005-04 — Audit Service: Immutable Platform Audit Log |
| Branch | `develop/v1.1` |
| Merge Commit | `946451222eaef3c988f80963e5eddce24ec7720e` |
| PR | #17 |
| Release Tag | `wp-005-04-audit-service-v1.0` |
| Tag Target | `946451222eaef3c988f80963e5eddce24ec7720e` |
| Frozen Status | IMPLEMENTED / MERGED / BASELINE FROZEN |

## Artifact Versions

| Artifact | Version |
|----------|---------|
| audit-service | 0.1.0 |
| identity-service | 0.1.0 |
| service-name template | 0.1.0 |
| reos-config | 0.1.0 |
| reos-common | 0.1.0 |
| reos-logging | 0.1.0 |
| reos-exceptions | 0.1.0 |

## Container Versions

| Image | Version / Tag |
|-------|---------------|
| CI build image | `registry.internal:5000/diep-lab:ee078c96125d371cf645249ff537383a67e291d6` |
| Baseline source tag | `wp-005-04-audit-service-v1.0` |
| Production push | Not performed in PCS-001; Stage 7 push remains deployment-ref and credential gated |

## CI Evidence

| Check | Result | Evidence |
|-------|--------|----------|
| Stage 1 — Lint & Type Check | PASS | GitHub Actions run `28740300083`, job `85221738736` |
| Stage 2 — SAST Security | PASS | GitHub Actions run `28740300083`, job `85221738742` |
| Stage 3 — Dependency Scanning | PASS | GitHub Actions run `28740300083`, job `85221738733` |
| Secrets Scanning | PASS | GitHub Actions run `28740300083`, job `85221738746` |
| Stage 4 — Unit & Component Tests | PASS | GitHub Actions run `28740300083`, job `85221785446` |
| Stages 5/6/7 — Build, Scan, Push | PASS | GitHub Actions run `28740300083`, job `85221850673` |
| CodeQL | PASS | Check run `85221840383` |

## Security Evidence

| Control | Status |
|---------|--------|
| Bandit | PASS |
| CodeQL | PASS |
| pip-audit | PASS |
| Trivy CRITICAL/HIGH image gate | PASS |
| Gitleaks PR diff scan | PASS |
| Sensitive logging CodeQL findings | Remediated before merge |

## Governance Evidence

| Record | Status |
|--------|--------|
| AR-052 | CLOSED — APPROVED / MERGED / BASELINE FROZEN |
| EECR-CHG-067 | CLOSED |
| EECR-CHG-068 | CLOSED |
| EECR-CHG-069 | CLOSED |
| EECR-CHG-070 | CLOSED |
| EECR-CHG-071 | CLOSED |
| EECR-CHG-072 | CLOSED |
| EECR-CHG-073 | CLOSED |

## Carry-Forward Conditions

The following are not merge blockers and remain controlled technical debt before first staging deployment:

| Condition | Disposition |
|-----------|-------------|
| C-AR052-02 | Populate or remove `audit_kafka_consumer_lag` |
| C-AR052-03 | Add hash-chain serialisation guard for same-actor REST writes |
| C-AR052-05 | Confirm audit-service port 8004 |
| C-AR052-06 | Confirm `chain_state` UPDATE permission |

