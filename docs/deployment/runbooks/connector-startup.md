# OA-098 — Connector Startup Runbook

## Status

APPROVED (PAO-026)

## Scope

This runbook covers the staged startup sequence for the three external-integration
connectors: SCADA (OPC-UA), GIS, and AMI. It applies to staging environments only.
Production deployment remains denied pending PAO-027 or equivalent governance approval.

## Prerequisites

- Target environment confirmed and change reference recorded.
- Source commit and image digests confirmed against governance baseline.
- Environment configuration and secret references validated (connector endpoints, TLS
  certificate paths, ingestion API credentials).
- Core platform services healthy: TimescaleDB, Redis, Kafka, ingestion API.
- Regression suite passing on the deployment candidate (`python3 -m pytest tests/`).

## Startup Sequence

### 1. Confirm core platform health

Verify all upstream dependencies are reachable before starting any connector:

- TimescaleDB: psql connectivity and table accessibility.
- Redis: PING response.
- Kafka: topic existence and broker reachability.
- Ingestion API: `/readyz` returns 200.

Do not proceed if any dependency is unhealthy.

### 2. Start SCADA connector

1. Confirm OPC-UA server endpoint and certificate references in configuration.
2. Start the SCADA connector process or container.
3. Confirm the connector health endpoint responds: `GET /health` → 200, `status: UP`.
4. Confirm the connector has established an OPC-UA session: `session_count ≥ 1`.
5. Record startup evidence: connector ID, source commit, start timestamp, session count.

### 3. Start GIS connector

1. Confirm GIS system endpoint and identity map configuration.
2. Start the GIS connector process or container.
3. Confirm the health endpoint: `GET /health` → 200, `status: UP`.
4. Confirm initial topology batch processed or buffer is accepting input.
5. Record startup evidence.

### 4. Start AMI connector

1. Confirm AMI system endpoint and meter identity map configuration.
2. Start the AMI connector process or container.
3. Confirm the health endpoint: `GET /health` → 200, `status: UP`.
4. Confirm the connector is accepting events: `events_submitted ≥ 0` (counter accessible).
5. Record startup evidence.

### 5. Validate all connectors healthy

After all three connectors have started:

- All connector `/ready` endpoints return 200.
- Connector Prometheus metrics are accessible at `/metrics` (if prometheus_client present).
- No dead-letter queue entries within the first 60 seconds.
- Log stream shows no ERROR-level entries for connection establishment.

### 6. Record startup evidence

| Field | Value |
| --- | --- |
| Operator / automation identity | |
| Environment | |
| Source commit | |
| SCADA connector start timestamp | |
| GIS connector start timestamp | |
| AMI connector start timestamp | |
| All /ready 200 confirmed at | |
| Validation outcome | PASS / FAIL / CONDITIONAL |
| Exceptions or follow-up actions | |

## Acceptance Criteria

- All three connectors report `/health` status `UP` within 120 seconds of startup.
- `/ready` returns 200 for all three connectors.
- No DLQ entries after initial connection establishment.
- Metrics endpoint reachable (200 or 503 if prometheus_client absent; either is acceptable).

## Failure Response

If any connector fails to reach `UP` within 120 seconds, do not continue — execute the
Connector Recovery Runbook or Rollback Procedure as appropriate.
