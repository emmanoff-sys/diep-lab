# OA-054 Platform Observability Standards

## Status

COMPLETE

## Observability Principles

Production observability shall be engineering-facing, deterministic, and
read-only. It must report platform health without changing runtime state or
introducing operator-facing application capability.

## Structured Logging

All platform services shall emit structured logs with the following minimum
fields:

| Field | Requirement |
| --- | --- |
| `timestamp` | UTC timestamp in ISO-8601 form |
| `level` | `debug`, `info`, `warning`, `error`, or `critical` |
| `service` | Stable service name |
| `environment` | Deployment environment |
| `event` | Noun-verb event name |
| `correlation_id` | Request, job, or workflow correlation id where available |
| `tenant_id` | Tenant or `default` when single-tenant |
| `component` | Runtime component or module |
| `outcome` | `success`, `failure`, `skipped`, or `unknown` |

Logs must not contain secrets, raw credentials, private keys, or sensitive
operator tokens.

## Metrics

Metrics shall be Prometheus-compatible where applicable.

Required metric categories:

- service availability and readiness;
- request count, latency, and error rate for APIs;
- background job count, duration, and failure rate;
- topology import session status and duration;
- ADMS advisory computation duration and outcome;
- persistence connection health;
- queue consumer lag and broker availability;
- backup freshness and restore verification status;
- deployment rehearsal status and validation score.

Existing readiness and deployment gauges include:

- `diep_readiness_score`;
- `diep_readiness_pass`;
- `diep_readiness_last_run_timestamp_seconds`;
- `diep_readiness_check_status`;
- `diep_deployment_status`;
- `diep_deployment_duration_seconds`;
- `diep_deployment_validation_score`;
- `diep_deployment_last_run_timestamp_seconds`.

## Distributed Tracing

Distributed tracing is required where the hosting environment provides tracing
collection. Trace propagation shall include:

- ingress request id;
- internal service call correlation id;
- topology import session id;
- advisory evaluation id;
- deployment rehearsal id.

Tracing is not required for pure in-process unit tests or local documentation
validation.

## Health Endpoints

Each deployable service shall provide:

| Endpoint Type | Purpose |
| --- | --- |
| Liveness | Process is alive and should not be restarted |
| Readiness | Service dependencies are sufficient to receive traffic |
| Deep health | Engineering diagnostic view of dependent services |

Health endpoints must be safe to call repeatedly and must not mutate business
state.

## Service Status Reporting

Status reports shall include:

- service name and version;
- environment;
- dependency status;
- latest readiness check result;
- latest deployment rehearsal result;
- active known limitations.

## Alert Definitions

Minimum alert set:

| Alert | Trigger | Severity |
| --- | --- | --- |
| API unavailable | Readiness endpoint fails for two consecutive intervals | Critical |
| Persistence unavailable | Database connectivity fails | Critical |
| Kafka unavailable | Broker or exporter unreachable | Critical |
| Redis unavailable | Redis ping fails | Warning or Critical by dependency |
| Backup stale | Newest backup exceeds governed age threshold | Critical before go-live |
| Restore verification stale | No successful restore verification in the governed window | Critical before go-live |
| Import failure spike | Topology import failures exceed SLO budget | Warning |
| Advisory failure spike | Advisory service failures exceed SLO budget | Warning |
| Deployment rehearsal failed | Latest rehearsal status is `NO_GO` | Critical before go-live |

## Service Level Objectives

Initial production-readiness SLOs:

| Capability | Objective |
| --- | --- |
| API availability | 99.5 percent monthly availability after go-live |
| Readiness check freshness | Latest successful readiness assessment within 24 hours |
| Backup freshness | Latest backup within 24 hours |
| Restore verification | Successful restore rehearsal before go-live and after material persistence changes |
| Advisory response | 95 percent of advisory requests complete within the governed service target once measured |
| Deployment rehearsal | 100 percent of release candidates require a PASS/GO rehearsal before production approval |

These SLOs are readiness targets and do not grant production go-live approval.

## Engineering-Facing Dashboards

Dashboards shall cover:

- platform overview;
- dependency health;
- ADMS runtime and import health;
- topology/state/operations/intelligence service health;
- readiness and deployment rehearsal history;
- backup and restore status;
- alert posture.

Dashboards are engineering-facing only under WP-013-01.
