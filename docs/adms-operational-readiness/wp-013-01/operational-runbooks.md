# OA-055 Operational Runbooks

## Status

COMPLETE

## Runbook Index

This document defines the operational runbook set required for WP-013-01. The
procedures are deliberately platform-focused and do not include operator
application workflows.

## Deployment Runbook

1. Confirm the target environment and change reference.
2. Confirm the source commit and container image digests.
3. Confirm environment configuration and secret references.
4. Run compile, lint, security, and regression validation.
5. Confirm database migration plan and rollback plan.
6. Confirm backup freshness and restore verification evidence.
7. Deploy to staging or rehearsal environment.
8. Run readiness and deployment rehearsal validation.
9. Record evidence and decision.

No production deployment is authorised by this runbook without separate
governance approval.

## Startup Procedure

1. Start stateful dependencies: database, Redis, Kafka, object storage.
2. Confirm dependency health.
3. Start ADMS runtime services.
4. Start topology, operational state, operations, and intelligence services.
5. Start FastAPI/readiness evidence services where applicable.
6. Start observability collectors and dashboards.
7. Run readiness assessment.
8. Record startup evidence.

## Shutdown Procedure

1. Place ingress or traffic routing into maintenance mode where applicable.
2. Drain in-flight requests.
3. Stop background workers after checkpoint completion.
4. Stop stateless application services.
5. Confirm no active topology import or deployment rehearsal is running.
6. Stop stateful dependencies only when backup and persistence posture has been
   confirmed.
7. Record shutdown evidence.

## Routine Operations

Daily checks:

- readiness score and failed checks;
- service health and restart counts;
- backup freshness;
- restore verification age;
- active alerts;
- persistence capacity;
- queue lag;
- security certificate and secret expiry windows.

Weekly checks:

- deployment rehearsal dry run in non-production;
- disaster recovery procedure review;
- access review for operational users;
- alert routing test;
- dashboard review.

## Backup Procedure

1. Confirm backup storage endpoint and credentials.
2. Run the governed backup job or confirm scheduled job completion.
3. Confirm backup artefact presence.
4. Confirm checksum or object integrity metadata where available.
5. Record backup timestamp, location, and retention class.
6. Alert if the backup age exceeds the governed SLO.

Existing repository mechanisms include `scripts/backup-db.sh`,
`scripts/backup-pg-basebackup.sh`, `scripts/verify-backup.sh`, and
`k8s/backup-cronjob.yaml`.

## Recovery Procedure

1. Declare recovery scope and target recovery point.
2. Isolate the target recovery environment.
3. Restore the selected backup to the recovery environment.
4. Apply WAL or point-in-time recovery where applicable.
5. Run data integrity checks.
6. Run readiness validation against the recovered environment.
7. Record recovery time, recovery point, limitations, and decision.

## Incident Response

1. Classify severity.
2. Assign incident lead.
3. Freeze non-essential changes.
4. Capture current readiness and observability evidence.
5. Apply the relevant recovery or mitigation procedure.
6. Record timeline and impacted components.
7. Produce post-incident review and follow-up actions.

## Maintenance Procedure

1. Announce maintenance window.
2. Confirm backups and rollback artefacts.
3. Apply maintenance in staging first.
4. Run readiness validation.
5. Apply maintenance to target environment only with governance approval.
6. Record evidence and residual risk.

## Upgrade Procedure

1. Confirm source and target versions.
2. Review migration and compatibility notes.
3. Confirm rollback plan.
4. Run regression suite.
5. Deploy to staging.
6. Execute deployment rehearsal.
7. Accept or reject upgrade based on evidence.

## Troubleshooting Guidance

| Symptom | First Checks |
| --- | --- |
| API readiness failure | FastAPI `/readyz`, database connectivity, Redis, Kafka, container restart count |
| Topology import failure | import session status, parser/mapping/validation logs, persistence health |
| Advisory failure | topology service health, operational state snapshot, operations audit trail |
| High latency | API latency metrics, database load, queue lag, CPU and memory saturation |
| Stale backups | backup job logs, object storage access, credentials, scheduler status |
| Failed deployment rehearsal | deployment validation summary, critical failures, rollback rehearsal evidence |

## Evidence Requirement

Every runbook execution shall record:

- operator or automation identity;
- environment;
- source commit or image;
- start and end time;
- validation outcome;
- exceptions and follow-up actions.
