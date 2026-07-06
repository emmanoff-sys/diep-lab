# R2-RISK-017 Closure Criteria
### DAEP / RE-OS | Binary Closure Gate | Revision 1.0 | 2026-07-06

## 1. Closure Decision

R2-RISK-017 may move to `RESOLVED` only when every criterion below is met. If any criterion is not
met, the risk remains `OPEN` or, after governance approval of the framework, `MITIGATED`.

## 2. Binary Criteria

| ID | Criterion | Required Evidence | Pass / Fail Rule |
|----|-----------|-------------------|------------------|
| R2V-001 | Test classification complete | `python scripts/release2/validate_test_classification.py` PASS | fail if any `test*.py` file is missing, stale, or duplicate |
| R2V-002 | Unit profile green | `release2-unit-tests` PASS | fail on any selected pytest failure |
| R2V-003 | Service integration profile green | `release2-service-integration` PASS | fail on any unaccepted service integration failure |
| R2V-004 | Database integration profile green | `release2-database-integration` PASS with DB readiness and migration logs | fail if DB hostname does not resolve, migrations fail, or DB-backed tests silently skip |
| R2V-005 | Legacy platform profile deterministic | `release2-legacy-platform` PASS under documented optional dependency profile | fail if tests depend on undeclared Prometheus/observability state |
| R2V-006 | Docker validation green | `release2-docker-validation` PASS | fail if Docker daemon unavailable, build fails, or image is not produced |
| R2V-007 | Security validation green | `release2-security-validation` PASS | fail on HIGH+ Bandit issue, unaccepted CVE, or secret finding |
| R2V-008 | Release gate summary complete | `release2-release-gate` PASS | fail if any mandatory profile job is missing or failed |
| R2V-009 | Governance approval recorded | QA, DevSecOps, EA, Release Manager, Programme Board sign-off | fail if any required approval is missing |

## 3. Allowed Statuses

| Status | Meaning |
|--------|---------|
| Open | Framework absent or evidence incomplete |
| Mitigated | Framework implemented and approved, but not all binary closure evidence has passed |
| Accepted | Programme Board accepts a named residual risk and explicitly authorizes continuation |
| Resolved | All binary criteria pass with evidence and approvals |

## 4. Current Recommended Status

After this framework implementation, R2-RISK-017 should move from `OPEN` to `MITIGATED` only after
human governance review accepts the framework. It should not move to `RESOLVED` until the dedicated
Release 2 validation workflow produces green evidence.
