# WP-013-01 Platform Operational Readiness

## Purpose

This evidence pack implements PAO-014 for EPIC-013 - Operator Applications,
WP-013-01 - Platform Operational Readiness.

The work package prepares the accepted ADMS platform foundation for deployment
enablement, operations, monitoring, support, and later operator-facing
applications. It does not add ADMS functionality.

## Authorised Baseline

| Field | Value |
| --- | --- |
| Programme Authorisation | PAO-014 |
| Epic | EPIC-013 - Operator Applications |
| Work Package | WP-013-01 - Platform Operational Readiness |
| Authoritative Branch | `develop/v1.1` |
| Baseline Commit | `5c28ca3fa2efe37cf5ca364e4650fc9c487c7e34` |
| Effective Date | 2026-07-09 |

The accepted WP-006 through WP-010 architecture remains frozen for this work
package. All readiness activity is additive.

## Objective Traceability

| Objective | Evidence | Status |
| --- | --- | --- |
| OA-053 - Production Deployment Architecture | `production-deployment-architecture.md` | COMPLETE |
| OA-054 - Platform Observability | `platform-observability-standards.md` | COMPLETE |
| OA-055 - Operational Runbooks | `operational-runbooks.md` | COMPLETE |
| OA-056 - Platform Resilience | `platform-resilience-validation.md` | COMPLETE |
| OA-057 - Production Security Readiness | `production-security-readiness.md` | COMPLETE |
| OA-058 - Deployment Rehearsal | `deployment-rehearsal.md` | COMPLETE |
| OA-059 - Operational Readiness Assessment | `operational-readiness-assessment.md` | COMPLETE |
| OA-060 - Final Operational Readiness Validation | `final-operational-readiness-validation.md` | COMPLETE |

## Scope Boundaries

This package is limited to deployment readiness, operational documentation,
operability standards, resilience procedures, security readiness review, and
rehearsal evidence.

The following remain out of scope:

- operator dashboards, consoles, workflow interfaces, mobile applications, and
  situational awareness UI;
- SCADA, GIS, OMS, AMI, or enterprise external integrations;
- automatic switching, switching execution, device control, SCADA writeback, or
  closed-loop automation;
- redesign of the WP-006 runtime, WP-007 topology services, WP-008 operational
  state, WP-009 operations, or WP-010 operational intelligence layers;
- production go-live approval.

## Existing Platform Evidence Reused

The readiness pack references existing repository capabilities where relevant:

- `fastapi/readiness.py` provides read-only readiness checks for FastAPI,
  PostgreSQL, Redis, Kafka, container health, disk use, memory use, and service
  uptime.
- `fastapi/deployment.py` provides read-only pre/post deployment validation and
  append-only evidence records.
- `tests/test_readiness_unit.py`, `tests/test_readiness_api.py`,
  `tests/test_deployment_unit.py`, and `tests/test_deployment_integration.py`
  validate the existing readiness and deployment evidence paths.
- `scripts/backup-db.sh`, `scripts/backup-pg-basebackup.sh`,
  `scripts/verify-backup.sh`, and `k8s/backup-cronjob.yaml` provide existing
  backup and verification mechanics.

## Completion Position

WP-013-01 is engineering-complete when the objective artefacts in this directory
are present, the objective traceability test passes, and the governed validation
suite records no regression in the accepted ADMS foundation.
