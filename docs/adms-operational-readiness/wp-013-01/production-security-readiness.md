# OA-057 Production Security Readiness

## Status

COMPLETE

## Security Review Scope

This review covers operational security readiness for deployment enablement. It
does not introduce new IAM functionality, external integrations, or operator
application access flows.

## Identity Management

Requirements:

- administrative access must use named identities;
- shared operational accounts are prohibited except for governed break-glass use;
- production access requires least privilege;
- access reviews are required before go-live and on a recurring schedule;
- service identities must be distinct from human identities.

## Secret Management

Requirements:

- secrets are not committed to source control;
- environment secrets are provided by the deployment secret manager;
- database, Redis, Kafka, object storage, and signing credentials are rotated
  through governed procedures;
- secret values are excluded from logs, metrics, readiness evidence, and
  deployment rehearsal records.

## Certificate Management

Requirements:

- external ingress uses TLS certificates from a governed issuer;
- internal mTLS may be adopted where the hosting environment supports it;
- certificate expiry is monitored;
- certificate renewal is rehearsed before go-live.

## Secure Configuration

Required controls:

- debug mode disabled outside local development;
- CORS restricted to approved origins;
- service ports limited to required exposure;
- administrative endpoints restricted to operator or engineering networks;
- deployment configuration is environment-specific and reviewed;
- default credentials are prohibited.

## Operational Trust Boundaries

| Boundary | Control |
| --- | --- |
| Public ingress to API | TLS, ingress policy, rate limits where applicable |
| Application to persistence | Private network, service identity, least privilege |
| Application to Kafka/Redis | Private network, credentialed access |
| Engineering observability | Restricted engineering access |
| Backup storage | Encrypted storage, restricted service identity |
| Rehearsal environment | Non-production data or approved anonymised data |

## Deployment Security Review

Before production go-live approval, the deployment must confirm:

- container images come from trusted build outputs;
- image digests are recorded;
- dependency and vulnerability scan results are reviewed;
- runtime service accounts are least privilege;
- secrets are injected by the environment and not baked into images;
- network policies or firewall rules match the architecture.

## Access Control Review

Access review must include:

- repository write access;
- deployment environment access;
- database administrative access;
- secret manager access;
- observability dashboard access;
- backup storage access;
- break-glass process and auditability.

## Security Limitations

The following remain future or environment-specific actions:

- production IAM integration details depend on the selected hosting environment;
- certificate issuer and rotation automation require environment selection;
- production go-live security sign-off requires separate governance approval.

## Completion Criteria

OA-057 is complete when identity, secrets, certificates, secure configuration,
trust boundaries, deployment security, and access control review standards are
defined without adding unauthorised functional capability.
