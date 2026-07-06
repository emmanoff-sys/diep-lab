# Release 2 CI/CD Validation Architecture
### DAEP / RE-OS | Dedicated Validation Workflow | Revision 1.0 | 2026-07-06

## 1. Existing Workflow Finding

Existing workflows split validation across:

- `service-ci-cd.yml`: RE-OS services, shared libraries, scaffold, CodeQL, security, Docker build on
  push.
- `ci.yml`: legacy DIEP Docker build/scan and driver selftests.
- auxiliary workflows for infra, DAST, load, and DORA reporting.

This split is correct for Release 1 history, but it is insufficient for Release 2 because WP-006
touches legacy topology/CIM areas that are outside `service-ci-cd.yml` and broader than the current
driver-only scope in `ci.yml`.

## 2. Decision

Introduce a dedicated Release 2 validation workflow:

```text
.github/workflows/release2-validation.yml
```

The workflow is additive. It does not replace Release 1 service-ci or legacy CI. It exists to close
R2-RISK-017 by executing the governed profiles defined in
`RELEASE-2-VALIDATION-FRAMEWORK.md`.

## 3. Trigger Model

| Trigger | Purpose |
|---------|---------|
| `workflow_dispatch` | formal R2-RISK-017 closure runs and board evidence |
| `pull_request` to `develop` or `main` touching Release 2 validation, topology, CIM, tests, or workflows | early evidence |
| `push` to `develop` touching same paths | post-merge confidence |

## 4. Job Architecture

| Job | Depends On | Purpose | Artifacts |
|-----|------------|---------|-----------|
| `release2-classification` | none | validate every test file is classified | classification log |
| `release2-unit-tests` | classification | run pure unit profile | JUnit XML, pytest log |
| `release2-service-integration` | classification | run service integration profile with service dependencies | JUnit XML |
| `release2-database-integration` | classification | run DB integration with Timescale/Postgres and SQL migrations | migration log, JUnit XML |
| `release2-legacy-platform` | classification | run deterministic legacy profile with optional observability policy | JUnit XML |
| `release2-docker-validation` | classification | verify Docker runner readiness, render Release 2 compose config, build legacy/API image, and capture scanner-ready image metadata | preflight JSONL, compose JSONL, masked compose config, build JSONL, build log |
| `release2-security-validation` | classification | run Bandit and pip-audit policy checks | JSON reports |
| `release2-release-gate` | all mandatory jobs | aggregate evidence and block next authorization unless all required jobs pass | gate summary |

## 5. Approval Requirements

The workflow alone does not authorize WP-006-03B. The following approvals are required:

- QA Lead accepts test profile results.
- DevSecOps Lead accepts Docker/security evidence.
- Enterprise Architect accepts architecture boundary and classification.
- Release Manager accepts R2-RISK-017 closure recommendation.
- Programme Board records the final GO / GO WITH CONDITIONS / HOLD / NO GO decision.

## 6. Artifact Retention

Artifacts required for closure:

- classification output,
- JUnit XML for all test profiles,
- migration/bootstrap log,
- Docker preflight JSONL, compose config evidence, build log, and image metadata,
- Bandit JSON,
- pip-audit JSON,
- Release Gate summary.

Artifacts should be retained by GitHub Actions under the default retention policy unless the
Programme Board requires a longer evidence archive.
