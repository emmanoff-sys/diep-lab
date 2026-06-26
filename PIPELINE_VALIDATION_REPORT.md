# DIEP — Pipeline Validation Report (Post-SIT Stabilization Sprint, Round 2)

Consolidated delta report for the 6-item sprint that followed the first
formal SIT (`SYSTEM_ACCEPTANCE_REPORT.md`, commit `869749c`, verdict **NOT
READY FOR CIM**). This report is the synthesis; the evidence lives in each
work item's own report section (cross-referenced below, not duplicated) and
in `validation/evidence/`. The final recommendation is in `READY_FOR_CIM.md`.

## Work item -> finding -> fix -> evidence

| # | SIT finding (Round 1) | Fix this sprint | Verified | Evidence |
|---|---|---|---|---|
| 1 | NaN measurement causes silent, total data loss | Explicit finiteness check; rejection + quality flag + audit log + metric, all four | Live: a NaN reading now produces a DB row with `rejected_reason=non_finite_value` | `INTEGRATION_VALIDATION_REPORT.md` §4.2; `ingestor/telemetry_ingestor.py` |
| 2 | Synchronous design loses MQTT keepalive under load, permanently dropping QoS-0 messages | Threaded queue (receive/validate/persist separated); bounded backpressure | Live: 0 permanent loss at every tested rate, 1-5000 msg/s bursts (received == persisted, 9055 == 9055) | `PERFORMANCE_REPORT.md` §3.2 |
| 3 | (re-benchmark) | Burst + sustained-rate tests, CPU/memory capture (new) | Real sustainable ceiling ≈15 msg/s; bottleneck has moved downstream of the ingestor (TimescaleDB write path, 86.89% CPU at peak) — new, honest finding, out of this sprint's scope | `PERFORMANCE_REPORT.md` §3.3-3.6 |
| 4 | MDM's trusted stream has no consumer; broker ACL grants nothing on it | Repointed ingestor at `diep/+/+/trusted`; ACL fix (**readwrite**, not just read — see below) | Live: `OUT_OF_RANGE`/`INVALID` escalations now reach the DB, not just MDM's internal counters | `INTEGRATION_VALIDATION_REPORT.md` §4.2-4.3 |
| 5 | OPC UA connector isolated, no MQTT/Kafka path | New `mdm_consumer.py`; quality/timestamp/metadata propagation onto the existing `InternalMeasurement`/`MeasurementSink` surface | Live: published envelope -> `/health` shows correct value, `status_code`, both timestamps, full topology metadata, for both GOOD and escalated cases | `INTEGRATION_VALIDATION_REPORT.md` Scenario G; `services/opcua/VALIDATION.md` addendum |
| 6 | (re-validate) | Full scenario suite re-run + 1 new scenario | 91/91 checks passing | This report, §1 below |

## 1. Full scenario re-run

| Scenario | Round 1 | Round 2 |
|---|---|---|
| A — single meter | 17/17 | 17/17 (unchanged) |
| B — multiple meters | 21/21 | 21/21 (one transient test-isolation false alarm along the way — see `INTEGRATION_VALIDATION_REPORT.md` §4.4) |
| C — bad quality | 10/10 (asserted the bug) | 12/12 (assertions updated to the fixed behavior) |
| D — estimated values | 9/9 | 9/9 (unchanged) |
| E — duplicates | 4/4 | 4/4 (unchanged) |
| F — timestamps | 10/10 | 10/10 (unchanged) |
| Quality flags supplement | 6/6 | 6/6 (unchanged) |
| G — OPC UA trusted consumer (new) | — | 12/12 |
| **Total** | **77/77** | **91/91** |

## 2. The one finding this sprint surfaced that wasn't in the Round 1 list

Fixing the ACL the way the Round 1 finding literally described it (grant
`read` on the trusted topic) **did not work**. Direct testing — not just
re-reading scenario output — showed MDM's publish to that topic was itself
silently failing for lack of a `write` grant (same shared `ingestor`
identity for both publisher and subscriber), invisible to every log line
and counter either service exposes for a QoS-0 publish. Full root-cause in
`INTEGRATION_VALIDATION_REPORT.md` §4.3. This means the original Round 1
finding ("no consumer") was, in a precise sense, incomplete — there was
also no working publisher, for a different and less visible reason.

## 3. What this sprint did not touch (by design)

- Findings 4-6 from the original report (unscoped `/telemetry/latest`, MDM
  tenant-id reconciliation, DEBUG-level duplicate-drop logs) — not in this
  sprint's 6 work items.
- FastAPI's `/telemetry` endpoint and TimescaleDB's write path — identified
  this sprint (§ above, finding 3) as the *new* throughput ceiling, but
  fixing it was never one of the 6 work items assigned.
- CIM/IEC 61968 implementation — explicitly out of scope per the sprint
  brief; nothing in this sprint moves toward it.
- A server-side OPC UA address space (`asyncua.Server`) — Work Item 5 asked
  the connector to *consume* trusted measurements, which it now does;
  re-publishing them as OPC UA nodes to external clients is a different,
  larger piece of work, explicitly deferred (see `services/opcua/VALIDATION.md`).

See `READY_FOR_CIM.md` for the final recommendation.
