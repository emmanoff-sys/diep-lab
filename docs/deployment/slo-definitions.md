# OA-098 — Connector SLO Definitions

## Status

APPROVED (PAO-026)

## Scope

Service Level Objectives for the three external-integration connectors (SCADA, GIS,
AMI) in staging environments. These SLOs define the acceptance criteria for OA-099
operational readiness validation. Production SLOs require separate governance definition.

## Connector Health SLOs

| SLO | Target | Measurement |
| --- | --- | --- |
| Startup health convergence | All connectors `status: UP` within 120 s of process start | `/health` endpoint, `healthy: true` |
| Readiness availability | `/ready` returns 200 within 30 s of health convergence | `/ready` endpoint |
| Liveness permanence | `/live` always returns 200, including during degraded state | `/live` endpoint — must never return non-200 |
| Metrics accessibility | `/metrics` responds (200 or 503) within 2 s | `/metrics` endpoint |

## Connector Reliability SLOs

| SLO | Target | Measurement |
| --- | --- | --- |
| Valid event acceptance rate | ≥ 99% of syntactically valid events with a resolved identity are accepted | `events_submitted / (events_submitted + events_rejected)` where rejection reason is not duplicate |
| Dead-letter rate for valid events | 0% — no valid, resolvable event shall be dead-lettered | `events_dead_lettered_total` counter should not increment for valid events |
| Dead-letter rate for invalid events | 100% — every translation failure or unresolvable identity shall be dead-lettered | Dead-letter queue count matches invalid-event injection count |
| Duplicate suppression | Duplicate events (same message_id) are suppressed without dead-lettering | `detail: "duplicate (skipped)"` result; DLQ count unchanged |
| Buffer overflow recovery | After overflow, subsequent valid events are processed without error | `buffer_overflow_total` may increment; `events_submitted` continues to increment |
| Backoff ceiling | Retry delay does not exceed `max_s` (default 300 s) regardless of retry count | `ExponentialBackoff.delay_for(n)` ≤ 300 s for all n |

## GIS-Specific SLOs

| SLO | Target | Measurement |
| --- | --- | --- |
| Batch translation success rate | ≥ 99% of batches with at least one resolvable node+edge pair produce output | `batches_dead_lettered_total / batches_processed_total` |
| Partial rejection tolerance | Batches with some unresolvable features are not dead-lettered if net output > 0 | `rejection_count > 0` but `dead_lettered: false` for partial batches |

## AMI-Specific SLOs

| SLO | Target | Measurement |
| --- | --- | --- |
| Meter identity resolution rate | ≥ 99% of messages with a meter_id in the identity map are accepted | `events_rejected_total` with reason `identity_not_found` = 0 for known meters |
| Message type acceptance rate | ≥ 99% of messages with a known message_type are translated successfully | `events_dead_lettered_total` does not increment for known message types |

## SLO Measurement Context

These SLOs apply to staging validation only. They are measured over the duration of
the OA-098 staging validation procedure and the OA-099 operational readiness
validation. They do not constitute production SLAs.

All SLO measurements shall be recorded in the OAR-010-WP-026-xx operational
acceptance record produced for PAO-026 closure.
