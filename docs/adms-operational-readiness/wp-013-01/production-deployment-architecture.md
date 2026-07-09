# OA-053 Production Deployment Architecture

## Status

COMPLETE

## Deployment Model

The ADMS platform is deployed as a containerised service set with clear
separation between application services, stateful dependencies, observability
services, and operational support tooling.

The production deployment model is:

- application services run as independently deployable containers;
- stateful dependencies run in managed or operator-controlled high-availability
  services;
- runtime configuration is injected through environment-specific configuration
  and secrets;
- readiness and deployment validation are read-only and evidence-producing;
- all operator-facing applications are deferred to WP-013-02.

## Runtime Hosting

Runtime hosting shall use immutable container images deployed into a governed
environment. Stateless ADMS application services may be replicated horizontally;
stateful dependencies are hosted through managed services or governed clustered
deployments with backup and restore evidence.

## Service Topology

| Layer | Components | Deployment Responsibility |
| --- | --- | --- |
| ADMS runtime | WP-006 topology import runtime and APIs | Existing accepted platform service |
| Topology services | WP-007 graph, query, tracing, outage, and simulation modules | Existing accepted platform service |
| Operational state | WP-008 state engine, repository, validation, and services | Existing accepted platform service |
| Operations support | WP-009 outage, isolation, switching advisory, restoration, audit | Existing accepted platform service |
| Intelligence | WP-010 simulation, rules, explanation, contingency, restoration optimisation | Existing accepted platform service |
| Evidence APIs | `fastapi/readiness.py`, `fastapi/deployment.py` | Read-only readiness and rehearsal evidence |
| Persistence | PostgreSQL/TimescaleDB-compatible database | Managed or clustered stateful service |
| Cache and queue | Redis and Kafka-compatible services | Managed or clustered stateful services |
| Observability | Prometheus, Grafana, log aggregation, alert routing | Engineering-facing operational tooling |

## Environment Separation

| Environment | Purpose | Constraints |
| --- | --- | --- |
| Local development | Developer verification and unit tests | No production data |
| Integration | Cross-service validation and regression testing | Synthetic or anonymised data only |
| Staging | Deployment rehearsal and operational acceptance | Production-like configuration without production authority |
| Production | Future live operation | Not authorised by PAO-014 |

Promotion from staging to production requires separate governance approval. This
work package does not grant go-live approval.

## Container Orchestration Approach

The platform supports two governed hosting patterns:

- Docker Compose or equivalent local orchestration for development and
  controlled rehearsal.
- Kubernetes-compatible orchestration for production-like deployments, using the
  existing `k8s/` manifests as the current repository substrate.

Production orchestration shall provide:

- rolling replacement or blue/green rollout for stateless services;
- health probes before traffic admission;
- persistent volume and backup controls for stateful services;
- secrets mounted from the environment secret manager;
- resource requests and limits for application and support services.

## High-Availability Topology

| Component | HA Requirement | Readiness Position |
| --- | --- | --- |
| API/runtime containers | At least two replicas in production-like environments | Required before go-live |
| PostgreSQL/TimescaleDB | Primary/standby or managed HA with point-in-time recovery | Required before go-live |
| Redis | Sentinel, managed HA, or equivalent failover | Required before go-live |
| Kafka | Multi-broker or managed equivalent | Required before go-live |
| Object storage/backups | Durable replicated storage | Required before go-live |
| Observability | Redundant scraping and retained metrics/logs | Required before go-live |

## Network Architecture

Network boundaries:

- public ingress terminates at an ingress controller or load balancer;
- internal application traffic is isolated on service networks;
- database, Redis, Kafka, and object storage endpoints are private;
- administrative access uses controlled operator networks;
- observability endpoints are engineering-facing and not public by default.

Required controls:

- TLS for external ingress and administrative channels;
- service-to-service traffic restricted by network policy or equivalent firewall
  controls;
- no SCADA writeback, device control, or external utility integration endpoint
  is introduced by this work package.

## Infrastructure Assumptions

The deployment architecture assumes:

- container runtime or Kubernetes-compatible orchestrator is available;
- a managed or governed PostgreSQL-compatible datastore is available;
- Redis and Kafka are available as managed services or governed cluster
  deployments;
- object storage is available for backup artefacts;
- Prometheus-compatible metrics collection is available;
- log aggregation and alert routing exist before production go-live;
- secret and certificate management are provided by the hosting environment.

## Validation

Architecture validation is satisfied when:

- all authorised components are mapped to a deployment layer;
- every stateful component has an HA and backup position;
- every environment has a defined purpose and boundary;
- no prohibited WP-013-02, external integration, or control capability is
  introduced.
