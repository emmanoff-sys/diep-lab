# DIEP — Integration Validation Report (System Integration Test, 2026-06-25)

First formal System Integration Test (SIT) of the OT→IT pipeline, run against
the live stack (not a separate test environment). Companion reports:
`PERFORMANCE_REPORT.md`, `PIPELINE_LATENCY_REPORT.md`, `DATA_QUALITY_REPORT.md`,
`SYSTEM_ACCEPTANCE_REPORT.md` (verdict).

## 0. Headline finding — the architecture under test is not one pipeline, it's three

The sprint's architecture diagram describes a single chain: AMI → Canonical
Contract → MDM → Trusted Measurements → OPC UA Connector → FastAPI →
TimescaleDB → Portal/Grafana. **That chain does not exist as wired.** Verified
directly (not inferred) before writing any test:

- `grep` across the codebase: nothing outside MDM's own package subscribes to
  `diep/+/+/trusted`. FastAPI has no MQTT subscriber at all (`grep` for
  `on_message`/`client.subscribe` in `fastapi/app.py` returns nothing — its
  only MQTT-related code is a TCP-port security probe).
- The broker's ACL (`mosquitto/config/acl`, inspected directly): no identity
  — including the one MDM authenticates as — has a `write` grant on any
  `diep/+/+/trusted` topic, and no identity has a `read` grant on it either.
  `diep/+/+` (3 segments) does not match a 4-segment topic, so this isn't a
  near-miss; it's simply not provisioned.
- The OPC UA connector (Phases 1-3) has no MQTT/Kafka publishing at all by
  its own prior, explicit scope, and there is no OPC UA server anywhere in
  this stack for it to read from.

What's actually wired end-to-end is: **DLMS/device simulators → MQTT →
ingestor → FastAPI → TimescaleDB → Portal/Grafana/Prometheus**, carrying
*raw* telemetry (driver-assigned quality only, no MDM processing). MDM runs
as a second, independent subscriber to the same raw topic, producing a
quality-processed "trusted" stream that currently terminates at the broker
with no reader. This report validates each of those pieces for what it
actually does, not what the diagram assumes; `SYSTEM_ACCEPTANCE_REPORT.md`
covers the CIM-readiness implications.

## 1. Method

- Live stack, not a separate environment. SIT-prefixed synthetic fixtures
  (`SIT-METER-001..006`, two tenants, a feeder/transformer chain in
  `grid_nodes`) registered additively (`validation/scripts/00_fixtures.sql`)
  — see `git log` / this sprint's commit for the exact rows.
- Telemetry injected as real `contracts.TelemetryEnvelope` objects (the
  actual frozen contract class, not hand-typed JSON), published over the
  live mTLS broker using the already-provisioned `METER001` device
  certificate (reused rather than provisioning a new identity — the
  envelope's own `device_id` field, not the MQTT topic, is what the
  ingestor/MDM key off of).
- MDM was started against the live broker for this sprint (it was never
  deployed before — `docker-compose-mdm.yml` assumed a plaintext 1883
  listener that has not existed since Phase 9J-S4; fixed to use mTLS,
  reusing the `ingestor` identity's cert since its ACL grant — `topic read
  diep/+/+` — is exactly MDM's own subscription).
- MDM's per-scenario assertions mostly use **direct invocation**
  (`services.mdm.pipeline.MdmPipeline().process(...)` inside the running
  `diep-mdm` container) rather than a live broker round-trip, because the
  ACL gap above means a live publish-and-subscribe-back test is structurally
  impossible right now — confirmed, not assumed. Where MDM's behavior is
  genuinely stateful across messages (duplicate detection, out-of-order
  sequence tracking), the live, already-running service or a single batched
  invocation was used instead so the relevant state actually persists across
  calls — see `validation/scripts/harness.py`.
- All scenario scripts are committed at `validation/integration/scenario_*.py`
  and were re-run to produce the numbers below; raw output is captured under
  `validation/evidence/`.

## 2. Scenario results

| Scenario | Checks | Result |
|---|---|---|
| A — single meter, every value/timestamp/quality flag | 17/17 | PASS |
| B — multiple meters: ordering, throughput*, tenant isolation | 21/21 | PASS |
| C — bad quality: INVALID / OUT_OF_RANGE / COMMUNICATION_FAILURE | 10/10 | PASS (one finding redefined the test — see §3) |
| D — estimated values survive the pipeline | 9/9 | PASS |
| E — duplicate packets: detection, metrics, audit | 4/4 | PASS (with an audit-trail finding — see §3) |
| F — out-of-order / late / clock-drifted / future timestamps | 10/10 | PASS |
| Quality flags supplement (SUBSTITUTED/MISSING/DUPLICATE) | 6/6 | PASS |
| **Total** | **77/77** | |

\* Scenario B's own "throughput" sub-check was discarded after it became
clear it was measuring this harness's container-per-message overhead
(~2-3s/message), not the pipeline — real throughput is in
`PERFORMANCE_REPORT.md`.

### Scenario A — single meter

Published one envelope (voltage=231.7V, current=12.34A, power_kw=2.851kW,
frequency=50.02Hz, all GOOD) for `SIT-METER-001`. Verified bit-for-bit in
TimescaleDB (`telemetry.voltage/current/power_kw/frequency` columns) and in
MDM's trusted output (direct invocation): every value, the per-field quality/
estimated flags, `tenant_id`, and `correlation_id` round-tripped exactly.
MDM's enrichment correctly resolved `feeder_id=SIT-FDR-01` /
`transformer_id=SIT-TX-01` via a real graph walk over `grid_nodes` (not a
fabricated result — see `DATA_QUALITY_REPORT.md` §3).

One real fixture bug surfaced and was fixed mid-run (with explicit
confirmation before the UPDATE): `SIT-METER-001..005` were registered without
`devices.tenant_id`, defaulting to `'default'` — causing a genuine mismatch
between the envelope's self-reported `tenant_id` (`sit-tenant`) and MDM's
registry-derived `mdm.device_metadata.tenant_id`. After registering a
`sit-tenant` row and setting it on the fixture devices, this passed — but the
underlying behavior is worth flagging on its own: **MDM does not cross-check
the envelope's self-reported `tenant_id` against the device registry's
authoritative one.** They happened to agree here because the fixture was
corrected; in production they could legitimately disagree (a spoofed or
misconfigured device claiming another tenant's ID) with nothing detecting it.
See `SYSTEM_ACCEPTANCE_REPORT.md` recommendations.

### Scenario B — multiple meters

6 meters (`SIT-METER-001..005` under tenant `sit-tenant`, `SIT-METER-006`
under `sit-tenant-b`), each with a distinct verifiable value and
`sequence_number`, published in a burst. Every row landed attributed to the
correct device with the correct tenant — no cross-device value bleed, no
cross-tenant attribution. A second pass sent 3 sequential updates to one
device (seq 3000→3002): all 3 persisted as separate rows in the order sent
(none overwritten).

Tenant isolation note: this confirms *data is tagged correctly* once
written. It does **not** confirm a tenant-scoped telemetry read API exists —
checked directly: `GET /telemetry/latest` (the only generic telemetry read
route) takes no `device_id`/tenant parameter and returns the single
platform-wide latest row regardless of caller identity. Asset/onboarding
routes do enforce `_assert_tenant_access`; telemetry reads do not. This is a
real gap distinct from write-side correctness — see `SYSTEM_ACCEPTANCE_REPORT.md`.

### Scenario C — bad quality data

Two distinct cases, deliberately:

1. **Driver-pre-flagged** INVALID and COMMUNICATION_FAILURE: both survived
   unchanged through the DB metadata and through MDM (no transition
   recorded) — correct per MDM's "never overwrite a non-GOOD flag" rule.
2. **GOOD-flagged but actually bad** — this is where the architecture gap in
   §0 becomes concrete, not abstract:
   - `frequency=999Hz`, quality=GOOD: the DB shows `quality=GOOD` forever
     (the ingestor does not interpret quality at all). MDM correctly
     escalates it to `OUT_OF_RANGE` with an explicit, attributable
     transition (`reason=out_of_range`) — but that escalation only exists on
     the unreachable trusted topic.
   - `voltage=NaN`, quality=GOOD: **this is not a quality-flag question at
     all — it's silent data loss.** `requests` (used by the ingestor's
     `POST /telemetry`) refuses to serialize `NaN`
     (`InvalidJSONError: Out of range float values are not JSON compliant:
     nan`), the ingestor's `except requests.RequestException` catches it,
     logs an ERROR line, and **drops the reading — no retry, no
     dead-letter, no row in the DB at all.** MDM (direct invocation)
     correctly escalates the same reading to `INVALID`, but that too only
     reaches the unreachable trusted topic. A non-finite sensor reading
     today produces neither a row nor a quality flag in the system of
     record — only a log line.

### Scenario D — estimated values

`quality=ESTIMATED, estimated=False` sent deliberately to exercise the
contract's own auto-correction (`Measurement.__post_init__` forces
`estimated=True` when `quality=ESTIMATED`) — confirmed. Both the DB metadata
and MDM's trusted output preserved `quality=ESTIMATED`/`estimated=True`
unchanged, with no MDM transition recorded (correct — MDM never re-judges an
already-flagged value).

### Scenario E — duplicate packets

Published an identical envelope twice over the **live** broker (not direct
invocation — duplicate detection is in-process state that only means
something across messages within one running service). Results:

- Ingestor: exactly 1 DB row for 2 identical publishes (its own
  `_seen_envelopes` cache worked).
- MDM: `mdm_duplicates_total` (the real, live Prometheus counter) went
  `0 → 1` on the resend — confirmed via `curl localhost:9201/metrics`
  before/after, not inferred.
- **Audit finding:** neither service logs the drop above `DEBUG` level
  (`ingestor/telemetry_ingestor.py:204`, `services/mdm/mqtt_io.py:59`), and
  both run at `INFO` by default. Checked directly against real container
  logs from this exact test: neither log contains the word "duplicate" at
  INFO or above. The metric exists; an operator-visible audit trail does
  not, in either service.

### Scenario F — timestamp handling

Sent a sequence to one device: seq 10, 11, **9 (late arrival)**, 12, **13
(captured 5 min in the past)**, **14 (captured 5 min in the future)**, via a
single batched MDM invocation (state must persist across calls for
out-of-order detection to mean anything). All behaved correctly:
out-of-order correctly flagged only for the genuine straggler (seq 9);
seq 12 was *not* permanently desynced by it; drift was flagged by magnitude
in both directions (past **and** future), matching `abs(drift) > threshold`
in `services/mdm/timestamps.py`, not just lag. Every envelope still got an
`ingestion_timestamp` stamped regardless. Quality was unaffected in every
case (an orthogonal concern, correctly not conflated).

## 3. Environment notes worth recording

- This validation work had to move into a dedicated git worktree
  (`.claude/worktrees/dlms-driver-validation`) mid-sprint: the main
  checkout's branch was being switched by something else concurrently with
  this session (confirmed via `git reflog`, not assumed) — continuing in
  place risked losing track of which branch new files belonged to.
- `docker run --env-file` does not strip inline `#` comments the way `docker
  compose`'s `env_file:` directive does — `.env`'s `DB_PASSWORD` line has a
  trailing comment, which corrupted the password for one load-test
  container until worked around with a sanitized copy. Mechanical, not a
  credential problem, and confirmed without ever printing the secret.
- Every live-infrastructure action beyond the initially-scoped reads/fixture
  writes (MDM's broker credential, a fixture UPDATE, deploying the
  Prometheus scrape config to the main checkout's live-mounted file) was
  paused and explicitly confirmed before proceeding, not inferred from
  earlier, broader approvals.
