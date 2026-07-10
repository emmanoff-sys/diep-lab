# OA-098 — Connector Recovery Runbook

## Status

APPROVED (PAO-026)

## Scope

Recovery procedures for SCADA, GIS, and AMI connector runtime failures in staging
environments. Covers DLQ inspection, backoff reset, and connector restart. Production
use of this runbook requires separate governance approval.

## Recovery Scenarios

### Scenario 1: Connector reports DOWN (health check failure)

Symptoms:
- `GET /health` returns `status: DOWN` or `healthy: false`.
- `/ready` returns 503.

Steps:
1. Check the connector log stream for the most recent ERROR or WARNING entries.
2. Confirm that upstream dependencies are healthy (ingestion API `/readyz`, network
   path to external system).
3. If a transient network fault is suspected, wait for the exponential backoff cycle
   to complete — the connector retries automatically.
4. If the connector has not recovered after `max_s` (default 300 s), restart the
   connector process using the Startup Runbook.
5. Record the fault: onset time, log evidence, recovery action, restored-healthy time.

### Scenario 2: Dead-letter queue accumulation

Symptoms:
- Prometheus `*_events_dead_lettered_total` or `*_batches_dead_lettered_total` counter
  rising.
- DLQ count visible via connector metrics or internal inspection.

Steps:
1. Identify the DLQ entries: message IDs, source system, reason field.
2. Classify the failure mode:
   - **Identity map miss** — source system is sending identifiers not in the connector's
     identity map. Update the identity map and re-enqueue the affected messages.
   - **Translation failure** — malformed payload from the source system. Raise an
     issue with the source system operator; do not re-enqueue until payload format
     is corrected.
   - **Ingestion rejection (non-duplicate)** — downstream ingestion API rejected the
     translated event. Check ingestion API logs for the rejection reason.
3. After the root cause is resolved, drain the DLQ manually or by connector restart
   with the corrected configuration.
4. Confirm DLQ count drops to zero after drain.
5. Record: DLQ entry count, root cause, resolution, post-recovery DLQ count.

### Scenario 3: Buffer overflow

Symptoms:
- Prometheus `*_buffer_overflow_total` counter rising.
- Connector is enqueuing faster than it is processing.

Steps:
1. Confirm the connector process loop is not blocked (check log stream for stalls).
2. Confirm the downstream ingestion API is accepting events (check `/ready` and logs).
3. If ingestion is degraded, reduce upstream event generation rate or gate ingestion
   temporarily.
4. If the process loop is blocked, restart the connector after diagnosing the block.
5. Note: buffer overflow drops oldest events. After recovery, inspect DLQ for events
   that were translated but rejected due to staleness.

### Scenario 4: OPC-UA session loss (SCADA connector)

Symptoms:
- SCADA connector `/health` shows `session_count` not incrementing on reconnect.
- Log entries: session renewal failure, subscription restoration failure.

Steps:
1. Confirm the OPC-UA server is reachable from the connector host.
2. Confirm TLS certificate validity (see Certificate Lifecycle document).
3. The connector retries session establishment automatically with exponential backoff.
4. If no session is established within 5 minutes, restart the connector process.
5. After reconnect, confirm `session_count` incremented and events are flowing.

## Post-Recovery Validation

After any recovery action:

- All three connector `/ready` endpoints return 200.
- DLQ count is zero or falling.
- Buffer overflow counter has stopped incrementing.
- Connector metrics accessible at `/metrics`.
- Log stream shows no new ERROR entries for at least 2 minutes.

## Evidence Requirement

Every recovery execution shall record:

| Field | Value |
| --- | --- |
| Operator / automation identity | |
| Environment | |
| Affected connector(s) | |
| Fault onset time | |
| Recovery action taken | |
| Recovery completion time | |
| Post-recovery DLQ count | |
| Validation outcome | PASS / FAIL / CONDITIONAL |
| Follow-up actions | |
