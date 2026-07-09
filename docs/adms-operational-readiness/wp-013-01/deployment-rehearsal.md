# OA-058 Deployment Rehearsal

## Status

COMPLETE

## Rehearsal Principle

Deployment rehearsal is a controlled non-production exercise. It validates
deployment readiness and rollback confidence, but it does not authorise
production deployment.

## Environment Preparation

Required preparation:

- target staging or rehearsal environment identified;
- source commit and image digests recorded;
- configuration and secrets verified;
- backup artefact and restore path confirmed;
- observability endpoints available;
- rollback path documented;
- prohibited operator/control functionality absent.

## Deployment Validation

Validation sequence:

1. Confirm clean source baseline.
2. Build or select immutable images.
3. Apply configuration to rehearsal environment.
4. Start stateful dependencies.
5. Start application services.
6. Run health and readiness checks.
7. Run WP-006 through WP-010 regression slices.
8. Record results.

## Configuration Verification

Verify:

- environment variables match the target environment;
- secrets are referenced, not embedded;
- service endpoints are private where required;
- backup locations are configured;
- metrics and logs are routed;
- alert routes are active or explicitly simulated.

## Operational Smoke Testing

Minimum smoke tests:

- FastAPI readiness endpoint responds;
- database connectivity succeeds;
- Redis and Kafka checks pass or provide governed warnings;
- topology import health path is observable;
- topology/state/operations/intelligence regression slices pass;
- backup freshness check passes or records a governed warning;
- engineering dashboard data is visible.

## Rollback Rehearsal

Rollback rehearsal must prove:

- previous image or configuration can be restored;
- migrations are additive or rollback risk is explicitly accepted;
- service health returns to the prior known-good state;
- readiness evidence captures the rollback outcome;
- rollback does not mutate ADMS operational decisions or execute switching.

## Operational Acceptance Checklist

| Item | Required Evidence |
| --- | --- |
| Environment prepared | Environment identifier and configuration review |
| Deployment validated | Readiness and smoke test result |
| Configuration verified | Configuration checklist |
| Observability active | Metrics/log/dashboard evidence |
| Backup verified | Backup freshness and restore path |
| Rollback rehearsed | Rollback steps and outcome |
| Security reviewed | Secret, access, certificate, and trust-boundary review |
| Scope confirmed | No operator UI, external integration, or control execution |

## Completion Criteria

OA-058 is complete when the rehearsal process and acceptance checklist are
defined, repeatable, and evidence-producing.
