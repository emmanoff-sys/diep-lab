# DIEP — Pipeline Latency & Timestamp Consistency Report (SIT, 2026-06-25)

Covers sprint Deliverable 6. Distinct from `PERFORMANCE_REPORT.md` (which
covers end-to-end delivery latency *under load*): this report covers the
three-clock model the canonical contract defines, whether they stay
internally consistent, and MDM's own processing-latency metric, which is
real and live but separate from end-to-end delivery time.

## 1. The three clocks

`AMI_INGEST_PHASE4_CONTRACT.md` §5 and `contracts/telemetry.py` define three
distinct timestamps per envelope:

| Clock | Field | Set by | Verified this sprint |
|---|---|---|---|
| Device/gateway capture | `timestamp_utc` | the driver/gateway, before publish | Required, UTC-only, contract-enforced (`ContractValidationError` on a naive/non-UTC string — existing behavior, re-confirmed) |
| Ingestion | `ingestion_timestamp` | each independent consumer, on receipt | MDM stamps its own (it is its own MQTT consumer, not fed through the ingestor) — confirmed every envelope in Scenario F got one stamped, including the out-of-order/drifted/future cases |
| (implicit) DB write time | — | not separately recorded | **Finding:** `telemetry.time` is the envelope's own `timestamp_utc`, written verbatim by `ingest_telemetry()` (`insert_time = payload.time or datetime.now(...)`) — it is **not** the actual INSERT wall-clock time. There is no column anywhere recording when a row actually landed in TimescaleDB, separate from when the device says it captured the reading. This is why `PERFORMANCE_REPORT.md`'s latency numbers had to be measured by correlation-id polling from an external harness rather than read back from the `time` column. |

That last row is a real, structural finding: **the system of record cannot
answer "how stale is this row" from its own data** — only "when did the
device claim to capture it." For a meter with a wrong or drifted internal
clock, every database consumer (Portal, Grafana, ADMS) would see that wrong
timestamp with no way to detect the drift from the DB alone. MDM's
`timestamp_assessment` (drift/out-of-order flags) is the only place this is
actually checked — and it isn't reachable past the broker (see
`INTEGRATION_VALIDATION_REPORT.md` §0).

## 2. Clock drift and out-of-order — verified behavior (Scenario F)

Re-stated here with the specific numbers, since this report is the
timestamp-focused one:

| Case | drift_seconds (measured) | is_drifted | is_out_of_order |
|---|---|---|---|
| seq=10 (first seen) | ~0 | False | False |
| seq=11 (normal) | ~0 | False | False |
| seq=9 (late arrival, after seq=11 already seen) | ~0 | False | **True** |
| seq=12 (after the seq=9 straggler) | ~0 | False | False — not permanently desynced |
| seq=13, captured −300s (5 min in the past) | ≈ +300s | **True** (threshold 30s) | False |
| seq=14, captured +300s (5 min in the future) | ≈ −300s | **True** (threshold 30s) | False |

Two things worth calling out precisely: (1) out-of-order detection is
**sequence-number-based**, not timestamp-based — a late arrival with a
plausible timestamp is still caught because its `sequence_number` is behind
what's already been seen for that `(tenant_id, device_id)`; (2) drift is
checked by **magnitude** (`abs(drift_seconds) > threshold`), so a future
timestamp is flagged exactly like a stale one — confirmed both directions
fire, not just lag.

## 3. Processing latency (MDM's own, real, live metric)

`mdm_processing_latency_seconds` is a live Prometheus histogram on the
running `diep-mdm` service (not a direct-invocation number — this reflects
real envelopes received off the live broker during this sprint's testing).
Snapshot taken via `curl localhost:9201/metrics`:

```
mdm_processing_latency_seconds_count 3087
mdm_processing_latency_seconds_sum   17.27130697996472
```

Mean ≈ **5.6 ms per measurement**, end-to-end through MDM's own pipeline
(validate → dedup → timestamp → gap → unit-normalize → quality-assess →
enrich → metrics). This is fast because device-metadata enrichment is
TTL-cached (`services/mdm/enrichment.py`, 300s default) — the DB is only hit
on a cache miss, not per message. This number describes **MDM's internal
processing cost only** — it does not include MQTT transport time or
anything downstream, since there is no downstream (§0 of the integration
report).

## 4. Arrival latency

"Arrival latency" (device → ingestor receipt) was not separately isolated
from "processing latency" (ingestor receipt → DB write) in this sprint's
measurements — `PERFORMANCE_REPORT.md`'s correlation-id-polling method
measures the combined publish-to-database-visible time, not a breakdown by
hop. Breaking this down would need either application-level tracing
(not present in `ingestor/telemetry_ingestor.py` today — no span/trace
instrumentation) or broker-side message timestamps. Flagged as unmeasured
rather than estimated.
