# DIEP — System Acceptance Report (First Formal SIT, 2026-06-25)

Covers sprint Deliverable 10 (Architecture Review) and the overall
READY/NOT READY FOR CIM verdict. Synthesizes
`INTEGRATION_VALIDATION_REPORT.md`, `PERFORMANCE_REPORT.md`,
`PIPELINE_LATENCY_REPORT.md`, `DATA_QUALITY_REPORT.md` — read those for
evidence; this report is the conclusion.

## Verdict: **NOT READY FOR CIM**

Not because any single component is broken — the platform-as-built does what
it was each individually scoped to do, and every component-level deliverable
in this sprint passed (77/77 integration checks, clean resilience recovery
across 5 services). It's **NOT READY** because the thing CIM would need to
sit on top of — a stable, quality-governed, standardized data layer — doesn't
exist yet as an integrated whole, and this sprint found two real bugs
(silent data loss, a low throughput ceiling) in the one path that *is* wired
end-to-end. Building a standards-translation layer on top of this now would
mean standardizing raw, ungoverned, occasionally-lossy data — which defeats
much of what CIM is for.

## 1. Architecture as built vs. as diagrammed

```
AS DIAGRAMMED (sprint brief):
AMI -> Canonical Contract -> MDM -> Trusted Measurements -> OPC UA -> FastAPI -> TimescaleDB -> Portal/Grafana

AS BUILT (confirmed by direct inspection, not assumed):
AMI -> Canonical Contract -> ingestor -> FastAPI -> TimescaleDB -> Portal/Grafana/Prometheus   [WIRED, validated this sprint]
AMI -> Canonical Contract -> MDM -> "trusted" topic -> (nobody)                                 [WIRED to nowhere]
(no OT source) -> OPC UA Connector -> (no publish path, by its own prior scope)                 [ISOLATED]
```

MDM and OPC UA are real, independently working components — this sprint
validated MDM's internal logic thoroughly (all 8 quality flags, dedup,
timestamp/drift, real topology enrichment) and confirmed OPC UA's connector
starts, holds health/metrics endpoints, and (per its own prior VALIDATION.md)
is logic-correct against the asyncua API surface. Neither is wired to
anything downstream. This is the single most important finding of this SIT.

## 2. Coupling and bottlenecks found

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | MDM's trusted stream has no consumer; broker ACL doesn't even grant the necessary read/write topics | **Blocking for CIM** | `INTEGRATION_VALIDATION_REPORT.md` §0 |
| 2 | A non-finite (NaN) measurement causes **silent, total data loss** at the ingestor — no retry, no dead-letter, no row, no alert | **Blocking** | `INTEGRATION_VALIDATION_REPORT.md` Scenario C |
| 3 | Ingestor's synchronous single-threaded design has a real throughput ceiling (~10-90 msg/s clean; severe loss beyond) and can be disconnected from the broker entirely under load, permanently losing QoS-0 messages in flight | **Blocking** (for any deployment beyond a handful of meters) | `PERFORMANCE_REPORT.md` §1 |
| 4 | No tenant-scoped telemetry read API (`/telemetry/latest` is global, unscoped) despite tenant-scoped writes and tenant-scoped asset APIs | High | `INTEGRATION_VALIDATION_REPORT.md` Scenario B |
| 5 | MDM does not reconcile a device's self-reported `tenant_id` against the device registry's authoritative one | High | `DATA_QUALITY_REPORT.md` §2.1 |
| 6 | No operator-visible audit trail for dropped duplicates in either the ingestor or MDM (logged at DEBUG, both run at INFO) | Medium | `INTEGRATION_VALIDATION_REPORT.md` Scenario E |
| 7 | `telemetry.time` is the device's self-reported capture time, not the actual DB write time — there is no way to measure data staleness from the DB alone | Medium | `PIPELINE_LATENCY_REPORT.md` §1 |
| 8 | OPC UA connector has no live OT data source and no publish path in this environment (by its own prior, explicit phase scope — not a new finding, restated for completeness) | Informational | prior sprint's `services/opcua/VALIDATION.md` |

Findings 1-3 are why this report does not recommend proceeding to CIM yet —
they mean the data CIM would standardize is not reliably complete (3, and to
a worse degree 2) and not quality-governed (1). 4-6 are real but don't block
CIM scoping; they're operational/security hardening items. 7 affects
observability, not correctness. 8 is already-known, already-documented scope.

## 3. What worked well (don't lose this in the findings list)

- The core ingestor → FastAPI → TimescaleDB → Portal/Grafana/Prometheus path
  is correct at the data level: every value, timestamp, and quality flag
  round-trips exactly for well-formed input (Scenarios A, B, D, and the
  quality-flags supplement — 53 checks, zero data-correctness failures).
- Infrastructure resilience is genuinely good: Redis, Kafka, FastAPI,
  TimescaleDB, and the MQTT broker all recovered cleanly from graceful
  restarts with no corruption, no crash loops, and (for TimescaleDB
  specifically) no recurrence of the documented incident's corruption
  signature.
- MDM's own internal logic — quality escalation rules, duplicate detection,
  out-of-order/drift detection, real topology enrichment — is solid and
  thoroughly exercised (this sprint's 77 checks plus the prior sprint's 61).
  The problem is exclusively that it isn't connected to anything, not that
  it's wrong.
- Both the ingestor and MDM reconnect to the broker automatically and
  correctly after a disconnect, including the unplanned overload-induced
  one this sprint triggered.

## 4. Recommendations, in order

1. **Wire MDM's trusted output into the path something actually reads, or
   explicitly decide not to and re-scope CIM around the raw path instead.**
   Either: (a) add the broker ACL grants MDM needs and point a real
   consumer at `diep/+/+/trusted`, or (b) if MDM's role is meant to be
   "advisory/observability only" rather than gating, say so explicitly in
   `PLANNING.md` — the current silence reads as an oversight, not a
   decision.
2. **Fix the NaN silent-data-loss bug** before any field deployment, not
   just before CIM — this is a correctness bug independent of this sprint's
   architecture question. Likely fix: validate finiteness before the
   `POST /telemetry` call (or reject earlier, at envelope parsing, with a
   visible reason) rather than letting `requests` raise deep inside the
   message-handling path.
3. **Address the ingestor's throughput ceiling** before scaling past a
   handful of meters: move the HTTP POST + DB write off the MQTT
   network-loop thread (a worker pool or async client), and reconsider QoS
   for telemetry if message loss during reconnect is unacceptable.
4. Add tenant-id reconciliation in MDM (flag, don't silently trust, a
   mismatch between envelope and registry).
5. Promote the duplicate-drop log lines to INFO, or add an explicit audit
   counter/event distinct from the Prometheus metric.
6. Once 1-3 are addressed, re-run this SIT's Scenario A-F suite (committed
   at `validation/integration/`) against the corrected pipeline before
   reconsidering the CIM verdict — the harness and fixtures are reusable,
   not one-off.

## 5. Scope discipline note

Per this sprint's explicit constraints, no architecture changes were made
to AMI, MDM, OPC UA, the database schema, or the FastAPI APIs to produce
this verdict — every finding above was observed against the system exactly
as built. The only changes made were: (a) fixing MDM's deployment config to
actually reach the mTLS-only broker (it was unreachable before this sprint,
unrelated to this sprint's findings — a deployment gap, not a code change),
(b) adding Prometheus scrape jobs + one Grafana dashboard for MDM/OPC UA
metrics that already existed but were never wired up, and (c) additive-only
test fixtures. All explicitly confirmed before being made; see
`INTEGRATION_VALIDATION_REPORT.md` §3.
