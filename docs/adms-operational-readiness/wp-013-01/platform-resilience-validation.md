# OA-056 Platform Resilience Validation

## Status

COMPLETE

## Resilience Scope

This objective validates operational resilience for the accepted ADMS platform.
It does not modify runtime behaviour.

## Backup Verification

Required evidence:

- latest database backup artefact exists;
- backup age is within the governed threshold;
- backup artefact is readable;
- backup location and retention are recorded;
- backup alerting is configured.

Existing repository checks:

- `fastapi/deployment.py::check_database_backups`;
- `tests/test_deployment_unit.py::test_database_backups_check`;
- `scripts/verify-backup.sh`.

## Restore Validation

Restore validation must be performed in a non-production recovery environment.

Required procedure:

1. Select a governed backup artefact.
2. Restore into an isolated recovery database.
3. Apply point-in-time recovery where available.
4. Run schema integrity checks.
5. Run readiness validation.
6. Record recovery point objective and recovery time objective evidence.

## Disaster Recovery Procedure

Minimum disaster recovery sequence:

1. Declare incident and recovery target.
2. Freeze writes to the impacted environment where possible.
3. Select the latest valid backup and WAL point.
4. Restore persistence into a clean environment.
5. Recreate application services from known image digests.
6. Rehydrate configuration from governed secret/config stores.
7. Run smoke validation and readiness assessment.
8. Record acceptance or escalate to governance.

## Operational Persistence Review

| Persistence Area | Readiness Position |
| --- | --- |
| Topology import persistence | Existing WP-006 runtime persistence retained |
| Network model repository | Existing WP-007 model access retained |
| Operational state | Existing WP-008 repository retained |
| Operations audit | Existing WP-009 audit path retained |
| Intelligence outputs | Existing WP-010 advisory outputs retained |
| Readiness evidence | Existing readiness/deployment evidence tables retained where present |

No persistence redesign is authorised under PAO-014.

## Failover Verification

Failover shall be verified in staging or equivalent:

- database failover or managed failover simulation;
- Redis failover or managed cache replacement simulation;
- Kafka broker unavailability simulation where safe;
- stateless service replica replacement;
- ingress reroute or load balancer target replacement.

Failover verification must record observed behaviour, recovery time, data
integrity result, and residual limitation.

## Recovery Objectives

Initial readiness targets:

| Objective | Target |
| --- | --- |
| Recovery Point Objective | 24 hours maximum until tighter operational SLOs are approved |
| Recovery Time Objective | 4 hours for platform restoration in staging rehearsal |
| Backup Freshness | 24 hours maximum |
| Restore Rehearsal | Required before production go-live approval |
| Data Integrity | No schema corruption or orphaned critical records after restore validation |

## Data Integrity Validation

Required checks after restore:

- database connectivity succeeds;
- migrations are at the expected revision;
- critical ADMS tables or repositories are readable;
- readiness assessment completes;
- representative WP-006 through WP-010 regression tests pass against the restored
  environment where applicable.

## Completion Criteria

OA-056 is complete when backup, restore, disaster recovery, persistence review,
failover verification, recovery objectives, and data integrity checks have a
defined operational standard and evidence path.
