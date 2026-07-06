# Release 2 Validation Framework
### DAEP / RE-OS | R2-RISK-017 Closure Framework | Revision 1.0 | 2026-07-06

## 1. Purpose

This framework defines the governed validation model required to close R2-RISK-017. It is a
release-engineering control package only. It does not authorize EPIC-006 continuation, EPIC-007, or
any business-functionality implementation.

## 2. Validation Profiles

| Profile | Purpose | Scope | Environment | Required Services | Execution Command | Expected Evidence | Required CI Job | Pass Criteria |
|---------|---------|-------|-------------|-------------------|-------------------|-------------------|-----------------|---------------|
| Unit Tests | Prove deterministic Python logic without live infrastructure | RE-OS libs/services unit tests and pure legacy unit tests classified as `unit-tests` | Python 3.12, no external services | none | `python scripts/release2/validate_test_classification.py --profile unit-tests --print-files \| xargs python -m pytest -q` | pytest log, JUnit XML, coverage where enabled | `release2-unit-tests` | all selected tests pass; classification manifest valid |
| Service Integration Tests | Prove service APIs and service-local integration behavior | tests classified as `service-integration` | Python 3.12, service test dependencies | PostgreSQL/TimescaleDB via testcontainers or CI service; Redis where service requires it; Kafka optional unless explicitly enabled | profile-selected pytest command | JUnit XML, service logs, container/service readiness output | `release2-service-integration` | all selected tests pass or documented optional broker tests remain skipped |
| Database Integration Tests | Prove topology/CIM/database-dependent validation paths | tests classified as `database-integration` | Python 3.12, DB env vars wired to CI services | TimescaleDB/PostgreSQL; SQL migrations applied | profile-selected pytest command after `sql/*.sql` bootstrap | migration log, pytest log, DB readiness evidence | `release2-database-integration` | DB hostname resolves; migrations apply; DB-backed tests execute rather than silently skip |
| Docker Validation | Prove container build path and image scan path | `fastapi/Dockerfile` and Release 2 applicable Dockerfiles | Docker-enabled runner with BuildKit | Docker daemon | `python scripts/release2/docker_validation.py preflight`; `python scripts/release2/docker_validation.py compose-config`; `python scripts/release2/docker_validation.py build --tag reos-r2-fastapi:${GITHUB_SHA}` | preflight JSONL, compose config evidence, build log, image ID, scanner-ready image reference | `release2-docker-validation` | daemon available; compose config renders; image builds; image metadata captured; vulnerability scan remains governed by the security profile/policy |
| Security Validation | Prove static/security dependency gates remain intact | Bandit, segmented pip-audit, CodeQL compatibility, secrets scan | GitHub Actions runner | none; network for advisory lookup | `python scripts/release2/security_dependency_audit.py --output-dir release2-pip-audit --summary release2-pip-audit-summary.json` plus workflow security commands | Bandit JSON, segmented pip-audit summary, per-surface pip-audit JSON, CodeQL/SARIF/secrets evidence | `release2-security-validation` | no HIGH+ SAST issue; every mandatory dependency surface audits cleanly; no unaccepted CVEs; no secrets |
| Legacy Platform Validation | Prove legacy platform tests run under a deterministic dependency profile | tests classified as `legacy-platform` | Python 3.12, legacy dependencies with governed optional observability policy | none unless test also classified database/release-gate | profile-selected pytest command | pytest log and optional-dependency policy evidence | `release2-legacy-platform` | all non-environment legacy tests pass under documented dependency profile |
| Release Gate Validation | Prove system/API smoke and deployment-adjacent checks before next authorization | tests classified as `release-gate` plus completed profile artifacts | governed CI environment only | running FastAPI stack, DB, Redis, Kafka as applicable | profile-selected pytest command after stack readiness | gate report, JUnit XML, service readiness logs | `release2-release-gate` | all mandatory profile jobs pass; explicit human approval recorded |

## 3. Test Classification

The authoritative test classification manifest is
`RELEASE-2-TEST-CLASSIFICATION.csv`.

The manifest is validated by:

```bash
python scripts/release2/validate_test_classification.py
```

No `test*.py` file under `tests/`, `libs/**/tests/`, or `services/**/tests/` may be unclassified.

## 4. Profile Execution Rules

- Unit and legacy pure tests must not require Docker, database, Redis, Kafka, or live HTTP services.
- Legacy platform tests must not rely on Docker-network DB hostnames such as `diep-timescaledb`.
- Legacy platform tests must set `PROMETHEUS_PROFILE=absent` unless a test explicitly validates
  `isolated-registry` behavior.
- Database integration tests must run only when the DB contract is satisfied.
- Docker validation must run on a Docker-enabled runner; local non-daemon machines are not valid
  evidence.
- Security validation must audit independent dependency surfaces separately. Mandatory runtime
  surfaces are Release 2 template runtime, audit-service runtime, and legacy DIEP runtime. Shared
  library, optional, and development-only scopes must be classified in
  the audit summary and must not leak into the runtime resolver input.
- Security validation must not exclude newly added Release 2 runtime dependencies from scanning
  unless an EECR-approved first-party/internal-package policy applies. First-party `reos-*` packages
  are excluded from public advisory-index input and recorded in segmented audit evidence.
- Release Gate validation is a governance decision point, not an implementation sprint.

## 5. R2-RISK-017 Control Effect

This framework converts R2-RISK-017 from an ambiguous broad-suite failure into named validation
profiles with binary evidence. R2-RISK-017 can close only when the closure criteria in
`RELEASE-2-R2-RISK-017-CLOSURE-CRITERIA.md` are met.
