# Release 2 Platform Recovery Backlog
### DAEP / RE-OS | R2-RISK-017 Recovery Backlog | Revision 1.0 | 2026-07-06

## R2-PLAT-001 - Validation Profile Pytest Isolation

| Field | Value |
|-------|-------|
| Title | Validation Profile Pytest Isolation |
| Problem Statement | Unit and service integration validation fail before test execution due pytest import-root collision between service-local `tests/conftest.py` modules. |
| Root Cause | Multi-package tests are batched into a single pytest invocation without isolating import roots or package contexts. |
| Scope | Release 2 validation orchestration, CI profile command structure, evidence commands. No application behavior changes. |
| Dependencies | Existing test classification manifest; Release 2 validation workflow. |
| Estimated Effort | 2-3 engineering days |
| Owner Role | QA Lead / Platform Test Engineer |
| Required Deliverables | Updated profile execution plan; isolated per-package invocation strategy; amended evidence commands; governance note explaining no feature impact. |
| Validation Evidence Required | Unit profile reaches execution and passes/fails on tests rather than import mismatch; service integration profile reaches execution and passes/fails on tests rather than import mismatch; JUnit XML produced for each isolated package group. |
| Exit Criteria | No `ImportPathMismatchError` in unit or service integration validation profiles. |
| Risk Reduction | Removes false-negative profile failures and restores trust in profile-selected pytest execution. |

## R2-PLAT-002 - Database Validation Substrate

| Field | Value |
|-------|-------|
| Title | Database Validation Substrate |
| Problem Statement | Database validation cannot bootstrap locally because DB client tooling is unavailable and no governed DB service is reachable. |
| Root Cause | The evidence environment does not provide the mandatory PostgreSQL/TimescaleDB service and client toolchain defined by the Release 2 environment contract. |
| Scope | CI runner service definitions, DB client installation, readiness checks, migration evidence. No schema or feature changes unless separately authorized. |
| Dependencies | Release 2 environment contract; SQL migration package. |
| Estimated Effort | 2-4 engineering days |
| Owner Role | DevSecOps Lead / DBA |
| Required Deliverables | Governed DB runner contract; DB readiness command evidence; migration bootstrap logs; CI service documentation. |
| Validation Evidence Required | `pg_isready` succeeds; `psql` available; TimescaleDB/PostgreSQL service reachable; migrations apply with `ON_ERROR_STOP=1`. |
| Exit Criteria | Database profile has a valid substrate before pytest starts. |
| Risk Reduction | Converts DB validation from environmental failure to executable integration evidence. |

## R2-PLAT-003 - Database Environment Contract Alignment

| Field | Value |
|-------|-------|
| Title | Database Environment Contract Alignment |
| Problem Statement | Audit-service integration tests fail during collection because `DB_DSN` is missing even when `DATABASE_URL` and legacy DB variables are present. |
| Root Cause | The Release 2 DB profile environment contract does not fully cover service-specific configuration names required by Release 1 services reused in Release 2 validation. |
| Scope | Environment contract mapping, CI environment variable definitions, profile evidence commands. No service configuration behavior changes unless separately approved. |
| Dependencies | R2-PLAT-002; audit-service configuration contract. |
| Estimated Effort | 1-2 engineering days |
| Owner Role | DevSecOps Lead / Service Platform Engineer |
| Required Deliverables | DB variable mapping table; profile env-var update proposal; evidence showing `DB_DSN` present; configuration traceability note. |
| Validation Evidence Required | Audit-service test collection succeeds in database and service integration profiles; no pydantic settings error for missing `DB_DSN`. |
| Exit Criteria | All DB-backed service tests receive the environment variables required by their settings classes. |
| Risk Reduction | Removes configuration drift between profile contract and service runtime contract. |

## R2-PLAT-004 - Docker Runner Readiness

| Field | Value |
|-------|-------|
| Title | Docker Runner Readiness |
| Problem Statement | Docker validation cannot run because the Docker daemon is unavailable. |
| Root Cause | The execution substrate provides a Docker client but not an operational Docker daemon. |
| Scope | CI runner selection/configuration, BuildKit readiness, Docker build evidence, image metadata capture. No Dockerfile changes unless separately authorized by verified build failure. |
| Dependencies | CI runner access; Release 2 validation workflow. |
| Estimated Effort | 1-3 engineering days |
| Owner Role | DevSecOps Lead / Release Engineer |
| Required Deliverables | Docker-enabled runner evidence; BuildKit readiness evidence; image build log; image ID/SHA record. |
| Validation Evidence Required | `docker info` succeeds; `docker build -t reos-r2-fastapi:<sha> fastapi/` succeeds; build artifact uploaded. |
| Exit Criteria | Docker validation profile passes on governed runner. |
| Risk Reduction | Restores mandatory container-build assurance without bypassing Docker validation. |

## R2-PLAT-005 - Legacy DB Hostname and Classification Recovery

| Field | Value |
|-------|-------|
| Title | Legacy DB Hostname and Classification Recovery |
| Problem Statement | Legacy platform validation still executes DB-dependent tests that assume `diep-timescaledb`, a Docker-network hostname unavailable from host execution. |
| Root Cause | Some legacy tests are classified or executed as legacy-platform tests even though they require DB infrastructure, and the hostname contract is environment-specific. |
| Scope | Test classification governance, DB-host contract, validation profile routing. No legacy business logic changes unless separately approved. |
| Dependencies | R2-PLAT-002; test classification manifest. |
| Estimated Effort | 2-3 engineering days |
| Owner Role | QA Lead / Legacy Platform Owner |
| Required Deliverables | Reclassification proposal for DB-dependent tests; hostname rule update; evidence that DB-dependent tests run only in DB profiles or with approved DB contract. |
| Validation Evidence Required | Legacy profile no longer fails on unresolved `diep-timescaledb`; DB-dependent tests either pass in DB profile or are formally documented as environment-dependent. |
| Exit Criteria | No ungoverned Docker-network hostname assumptions remain in mandatory non-DB profiles. |
| Risk Reduction | Separates true legacy test health from DB environment availability. |

## R2-PLAT-006 - Legacy Observability Dependency Determinism

| Field | Value |
|-------|-------|
| Title | Legacy Observability Dependency Determinism |
| Problem Statement | Legacy MDM and OPC UA tests fail when `prometheus_client` is present because metrics register duplicate collectors and some tests expect the dependency to be absent. |
| Root Cause | The legacy validation profile does not deterministically enforce `PROMETHEUS_PROFILE`, dependency presence, or isolated collector registry behavior. |
| Scope | Validation dependency profile, observability test execution policy, optional-dependency evidence. No telemetry feature changes unless separately authorized. |
| Dependencies | R2-PLAT-001; legacy dependency installation policy. |
| Estimated Effort | 3-5 engineering days |
| Owner Role | Platform Test Engineer / Observability Lead |
| Required Deliverables | Prometheus dependency policy; isolated-registry or absent-dependency evidence strategy; updated profile documentation; residual-risk proposal if full determinism requires code change. |
| Validation Evidence Required | MDM and OPC UA legacy tests produce deterministic results under the governed `PROMETHEUS_PROFILE`; no duplicate collector failures in mandatory profile. |
| Exit Criteria | Legacy profile is green or residual observability failures are formally accepted with documented containment. |
| Risk Reduction | Removes optional-dependency ambiguity from legacy validation. |

## R2-PLAT-007 - Security Dependency Audit Segmentation

| Field | Value |
|-------|-------|
| Title | Security Dependency Audit Segmentation |
| Problem Statement | pip-audit fails before CVE evaluation because multiple requirements surfaces are combined despite incompatible FastAPI pins. |
| Root Cause | Security validation treats independent dependency surfaces as one resolver input instead of auditing them as separate product surfaces or a deliberately resolved aggregate. |
| Scope | pip-audit invocation strategy, dependency-surface classification, security evidence artifact design. No dependency upgrades unless separately authorized by verified CVE or policy breach. |
| Dependencies | Dependency policy; security validation profile. |
| Estimated Effort | 1-2 engineering days |
| Owner Role | DevSecOps Lead / Security Engineer |
| Required Deliverables | Dependency surface audit matrix; separated pip-audit commands or resolved aggregate strategy; CVE evidence artifacts per surface. |
| Validation Evidence Required | pip-audit completes for each governed surface; no unaccepted vulnerabilities; artifacts uploaded per surface. |
| Exit Criteria | Security profile fails only on real vulnerabilities, not resolver conflicts. |
| Risk Reduction | Restores meaningful dependency security evidence. |

## R2-PLAT-008 - Release Gate Evidence Re-run and Governance Closure

| Field | Value |
|-------|-------|
| Title | Release Gate Evidence Re-run and Governance Closure |
| Problem Statement | R2-RISK-017 cannot close until all mandatory validation profiles produce accepted objective evidence. |
| Root Cause | Upstream validation profiles are not green, so the release-gate aggregation correctly fails. |
| Scope | Final governed validation run, evidence pack, closure report update, Programme Board recommendation. |
| Dependencies | R2-PLAT-001 through R2-PLAT-007 complete or residual risks formally accepted. |
| Estimated Effort | 1-2 engineering days |
| Owner Role | Release Manager / Programme Verification Board |
| Required Deliverables | Green Release 2 validation run or formal residual-risk acceptance; updated R2-RISK-017 closure report; updated risk register; authorization recommendation. |
| Validation Evidence Required | Release gate aggregation PASS, or explicit governance acceptance of every remaining non-green profile. |
| Exit Criteria | R2-RISK-017 moves to RESOLVED or ACCEPTED through objective evidence and governance approval. |
| Risk Reduction | Converts R2-RISK-017 from HOLD to a governed closure decision. |

