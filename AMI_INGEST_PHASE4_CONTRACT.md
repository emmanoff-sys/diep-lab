# AMI Ingest Phase 4 — MQTT/Kafka Telemetry Contract Specification

Canonical interface for every component that produces or consumes DIEP
telemetry. Implemented in code at `contracts/` (the source of truth — this
document describes what that package enforces, not the other way around).
Companion to `PLANNING.md` (sequencing), `DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md`
(the pre-Phase-4 ad-hoc contract this formalizes), and
`drivers/dlms/VALIDATION.md` (the driver this phase was built against).

**Status:** AMI Ingest (`drivers/dlms`) publishes this contract today.
Other drivers (battery, solar, charger, microgrid) remain on the legacy flat
payload until individually migrated — see §6. MDM/OPC UA/CIM do not begin
until this document is stable (`PLANNING.md` §1 gate).

---

## 1. Why a nested envelope, not flat fields

The requested field list (`tenant_id`, `device_id`, `measurement_type`,
`unit`, `value`, `quality`, `estimated`, ...) reads as one measurement per
message. The platform's existing shared edge loop
(`drivers/diep_driver/runner.py`, used by every current driver) publishes
**one MQTT message per device per read cycle**, carrying multiple canonical
fields (voltage, current, power_kw, frequency, ...) at once. Fanning that out
to one message per field would multiply the message rate for every driver on
the platform, not just the AMI/DLMS work this phase is scoped to.

**Resolution:** `TelemetryEnvelope` carries envelope-level fields once, plus a
`measurements` list of `Measurement` (`measurement_type`, `unit`, `value`,
`quality`, `estimated`) — one entry per field read that cycle. Every field in
the request is present; they're nested by level (envelope vs. per-point) so
per-point quality/estimated stays possible — the entire reason a quality
model exists — without changing the platform's message-per-cycle cadence.

---

## 2. MQTT Topic Contract

### 2.1 Topic hierarchy (implemented: `contracts/topics.py`)

| Category | Topic | Levels |
|---|---|---|
| Telemetry | `diep/<domain>/<device_id>` | 3 |
| Commands | `diep/<domain>/<device_id>/cmd` | 4 |
| Acks | `diep/<domain>/<device_id>/ack` | 4 |
| Alarms *(new)* | `diep/<domain>/<device_id>/alarm` | 4 |
| Device lifecycle *(new)* | `diep/<domain>/<device_id>/status` | 4 |
| Heartbeat *(new)* | `diep/<domain>/<device_id>/heartbeat` | 4 |

`domain` is the routing class (`meter`, `battery`, `solar`, `charger`,
`microgrid`), matching the existing `DOMAIN_MAP` in
`dispatcher/command_dispatcher.py` — unchanged, since changing it would
require every driver and the dispatcher to move in lockstep.

### 2.2 Meter namespace

For `domain=meter`, `device_id` is the registered device identity
(`devices.device_id` in TimescaleDB); `meter_id` (inside the envelope, not
the topic) is the physical meter serial/asset number, which may differ from
`device_id` when a meter is swapped but the logical device/service-point
identity is preserved. Today `meter_id` defaults to `device_id` (no swap
history exists yet) — see `BaseDriver.meter_id`.

### 2.3 Tenant isolation

Enforced **at the envelope level today**, not the topic path: `tenant_id` is
a mandatory, validated field on every `TelemetryEnvelope` (missing/empty
raises `ContractValidationError`); the ingestor's dedup key and any future
consumer's partitioning are tenant-scoped (`contracts/topics.py:partition_key`).
The broker itself is single-tenant in this deployment — no per-topic ACLs by
tenant exist yet. `contracts/topics.py:build_telemetry_topic_v2` defines the
target path-segmented layout (`diep/<tenant_id>/<domain>/<device_id>`) for
when broker-level multi-tenancy lands; **not wired to anything today** —
migrating the live topic strings is a separate, coordinated rollout (every
driver + the ingestor's wildcard subscription move together), not a Phase 4
change.

### 2.4 QoS / retained-flag policy (`contracts/topics.py:MQTT_TOPIC_POLICY`)

| Category | QoS | Retained | Why |
|---|---|---|---|
| telemetry | 0 | no | High frequency, loss-tolerant — the next reading supersedes a dropped one. |
| cmd | 1 | no | Must arrive; never retained (a retained stale command would replay on every new subscriber). |
| ack | 1 | no | Must arrive; not state. |
| alarm | 1 | no | Must arrive; an event, not a state snapshot. |
| status | 1 | **yes** | A new subscriber should see last-known online/offline immediately, not wait for the next transition. |
| heartbeat | 0 | **yes** | Cheap liveness check; retained so "is it alive" is answerable without waiting up to one interval. |

### 2.5 Wildcard subscription rules

```
diep/+/+            -> telemetry only (3 levels excludes every 4-level subtopic)
diep/+/+/cmd         -> all commands, any domain/device
diep/+/+/ack         -> all acks
diep/+/+/alarm       -> all alarms
diep/+/+/status      -> all lifecycle state
diep/+/+/heartbeat   -> all heartbeats
diep/<domain>/#      -> everything for one domain (telemetry + all subtopics)
```

The ingestor's existing `TELEMETRY_TOPIC = "diep/+/+"` subscription
(`ingestor/telemetry_ingestor.py`) needed **no change** — it already excludes
the new 4-level categories automatically.

---

## 3. Telemetry Payload Schema

Implemented in `contracts/telemetry.py` (Python, source of truth) and
mirrored in `contracts/schema/telemetry.schema.json` (JSON Schema 2020-12,
cross-language). Every field below is **required** unless noted.

| Field | Level | Type | Notes |
|---|---|---|---|
| `schema_version` | envelope | string `MAJOR.MINOR` | See §6. |
| `tenant_id` | envelope | string | See §2.3. |
| `site_id` | envelope | string | Maps to `sites.site_name`. |
| `device_id` | envelope | string | FK to `devices.device_id`. |
| `meter_id` | envelope | string | See §2.2. |
| `timestamp_utc` | envelope | ISO8601, UTC | See §5. |
| `timestamp_source` | envelope | `DEVICE`\|`GATEWAY`\|`INGEST` | See §5. |
| `source_protocol` | envelope | string | e.g. `dlms`, `modbus`, `opcua`. |
| `source_system` | envelope | string | e.g. `ami-ingest`. |
| `sequence_number` | envelope | non-negative int | Monotonic per `device_id`; dedup/ordering (§5). |
| `ingestion_timestamp` | envelope | ISO8601, UTC, **nullable** | Stamped by the ingestor on receipt — a driver must never set this. |
| `correlation_id` | envelope | UUID | Traces one reading across MQTT → ingestor → downstream. Auto-generated if omitted. |
| `measurements` | envelope | array, ≥1 item | See below. |
| `measurement_type` | per-point | string | e.g. `voltage`, `active_power`, `frequency`. |
| `unit` | per-point | string | e.g. `V`, `A`, `kW`, `Hz`. |
| `value` | per-point | number | |
| `quality` | per-point | enum, see §4 | |
| `estimated` | per-point | bool | Always `true` when `quality=ESTIMATED`; independently settable for e.g. `SUBSTITUTED`. |

`measurement_type` must be unique within one envelope's `measurements` array
(rejected otherwise — two simultaneous values for the same point in the same
reading is a producer bug, not data).

### Example payload (DLMS, as actually published by `drivers/dlms`)

```json
{
  "schema_version": "1.0",
  "tenant_id": "default",
  "site_id": "Abuja Site A",
  "device_id": "METER001",
  "meter_id": "METER001",
  "timestamp_utc": "2026-06-25T12:37:11.111219+00:00",
  "timestamp_source": "GATEWAY",
  "source_protocol": "dlms",
  "source_system": "ami-ingest",
  "sequence_number": 0,
  "ingestion_timestamp": null,
  "correlation_id": "beee56f6-062d-4a7a-a30c-afb484bc9ea9",
  "measurements": [
    {"measurement_type": "voltage",   "unit": "V",  "value": 230.0, "quality": "GOOD", "estimated": false},
    {"measurement_type": "current",   "unit": "A",  "value": 5.0,   "quality": "GOOD", "estimated": false},
    {"measurement_type": "power_kw",  "unit": "kW", "value": 1.0,   "quality": "GOOD", "estimated": false},
    {"measurement_type": "frequency", "unit": "Hz", "value": 50.0,  "quality": "GOOD", "estimated": false}
  ]
}
```

Note only 4 measurements, not 8 — see §3.1.

### 3.1 Fixing a latent data-quality bug while building this

The legacy flat payload (`drivers/diep_driver/normalize.py`) pads all 8
canonical fields to `0.0` for any driver that doesn't measure all of them —
making "really reads 0.0" indistinguishable from "this driver doesn't measure
this field at all" (the exact ad-hoc-ness `PLANNING.md` flags). Building the
envelope from `BaseDriver.measurement_units()` (only the fields a driver
declares units for) rather than the padded flat dict fixes this for any
driver that opts in: DLMS's envelope contains exactly 4 measurements, never a
phantom `solar_kw: 0.0`.

---

## 4. Quality Model

Implemented in `contracts/quality.py`. Mandatory on every `Measurement` —
this is the cross-layer correctness contract `PLANNING.md` §3 requires
("ADMS state estimation... must not silently treat MDM-estimated values as
ground truth"), now enforceable instead of merely documented.

| Flag | Meaning |
|---|---|
| `GOOD` | Device-reported, in-range, on time. The only flag where `is_measured` is true. |
| `ESTIMATED` | Interpolated/inferred, not device-measured. Forces `estimated=true`. |
| `SUBSTITUTED` | An operator/default value stood in for a real reading. |
| `INVALID` | Device reported a value but it failed validation. |
| `MISSING` | No value available for this measurement/interval. |
| `COMMUNICATION_FAILURE` | Could not reach the device/gateway. |
| `OUT_OF_RANGE` | Value present but outside the configured physical range. |
| `DUPLICATE` | Identical `(device_id, measurement_type, timestamp_utc, sequence_number)` already seen. |

`Quality.is_measured` (true only for `GOOD`) is what ADMS state estimation
should gate on per `PLANNING.md` §3 — not `is_usable_for_billing` (`GOOD` or
`SUBSTITUTED`), which is MDM's concern, not ADMS's.

---

## 5. Timestamp Rules

| Field | Authority |
|---|---|
| `timestamp_utc` | The capture time per `timestamp_source` — see below. **Must** be ISO8601, timezone-aware, UTC (`Z` or `+00:00`); naive or offset timestamps are rejected at construction. |
| `timestamp_source` | `DEVICE` (the meter's own clock — rare for DLMS today, the wire profile doesn't yet expose a device clock read), `GATEWAY` (the edge process's clock at read time — what `drivers/dlms` uses today), or `INGEST` (only ever set by the ingestor, for a payload that arrived with no usable upstream timestamp). |
| `ingestion_timestamp` | Set by `TelemetryEnvelope.stamp_ingestion_time()` in the ingestor on receipt. A driver-produced envelope always has this `null`; the contract doesn't reject a driver setting it, but nothing should rely on a driver-supplied value. |

**Late-arriving data:** store-and-forward (`Runner._buffer`, Phase 9A)
already buffers readings on the edge during an outage and replays them with
their original `timestamp_utc` intact on reconnect — `ingestion_timestamp`
will be much later than `timestamp_utc` for replayed readings, which is
correct and expected, not an error.

**Duplicate timestamps:** two measurements can legitimately share a
`timestamp_utc` only if they differ in `measurement_type` (enforced — see §3)
or `sequence_number` (a redelivery, not a new reading). `dedup_key()` =
`(tenant_id, device_id, timestamp_utc, sequence_number)` is the identity used
to drop redeliveries (`ingestor/telemetry_ingestor.py:_is_duplicate_envelope`)
— not `correlation_id`, which is per-publish-attempt, not per-reading, so it
changes across a retried publish of the *same* reading and can't be the
identity.

**Clock drift:** out of scope for Phase 4 (no NTP/clock-sync mechanism is
part of this contract). `timestamp_source=GATEWAY` is an explicit
acknowledgment that today's `timestamp_utc` is edge-gateway clock time, not
device clock time — consumers needing sub-second cross-device timing
alignment should not assume better than gateway-clock precision yet.

---

## 6. Versioning Strategy

`SCHEMA_VERSION = "1.0"` (`contracts/telemetry.py`), format `MAJOR.MINOR`.

- **Compatibility rule:** same `MAJOR` = compatible
  (`is_version_compatible()`). A consumer built against `1.0` must accept any
  `1.x` payload without modification.
- **Additive fields only within a MAJOR:** a `MINOR` bump may only add a new
  *optional* field (with a default) to `TelemetryEnvelope` or `Measurement`.
  Removing, renaming, or retyping any field — or making a previously-optional
  field required — is a `MAJOR` bump.
- **Deprecation policy:** a field slated for removal is marked deprecated in
  this document and in the field's docstring for at least one `MAJOR` cycle
  before actual removal in the next `MAJOR`. No field exists yet under
  deprecation.
- **Schema negotiation:** none today — there is one producer family
  (drivers opting into `use_contract_envelope`) and one consumer (the
  ingestor), both deployed from the same repo at the same revision. If/when
  MDM, OPC UA, or CIM consume this contract from a different deployment
  cadence, version negotiation (e.g. a consumer rejecting/quarantining a
  `MAJOR` it doesn't understand rather than guessing) becomes necessary —
  flagged here as a real gap for whichever of those phases lands first, not
  solved speculatively now.
- **Validation rule:** `TelemetryEnvelope.__post_init__` rejects construction
  outright if `schema_version`'s `MAJOR` doesn't match the running code's
  `SCHEMA_VERSION` `MAJOR` — a consumer never silently half-parses an
  incompatible payload.

---

## 7. Kafka Topic Contract — specification, not yet a wired pipeline

**Today's reality:** telemetry flows `device → MQTT → ingestor → HTTP POST →
FastAPI → TimescaleDB`. Kafka carries only `diep.commands`
(`fastapi/app.py` → `dispatcher/command_dispatcher.py`, pre-existing).
**No telemetry Kafka topic is produced or consumed by anything today.**

This section defines the topics the spec asks for (`contracts/topics.py`),
following the same Phase-0-before-build discipline as
`docs/opcua-discovery.md`: design and pin the contract now, build the actual
producer/consumer pipeline in a later, explicitly-scoped phase. Standing up a
second live telemetry pipeline mid-incident (this work landed immediately
after the 2026-06-25 host-instability recovery) was a deliberately *not*
taken architectural decision this pass — adding load/topics to a
freshly-recovered Kafka broker without separate sign-off would have been
scope creep on an already large change.

### 7.1 Topics (`contracts/topics.py:KAFKA_TOPICS`)

| Logical name | Topic | Retention | Notes |
|---|---|---|---|
| commands | `diep.commands` | 7d (unchanged) | Existing, wired. |
| telemetry | `diep.telemetry` | 7d | Not yet produced. |
| events | `diep.events` | 30d | General operational events. |
| alarms | `diep.alarms` | 30d | Mirrors the MQTT `alarm` topic for durable replay. |
| device_registration | `diep.device.registration` | **compact** | Full registry reconstructable from offset 0. |
| device_state | `diep.device.state` | **compact** | Latest known state per `device_id` (changelog, not a stream). |
| quality_events | `diep.quality.events` | 30d | Quality-flag *transitions* (e.g. a device going GOOD→COMMUNICATION_FAILURE), not every reading. |

### 7.2 Partitioning / key selection

`partition_key(tenant_id, device_id)` → `"<tenant_id>:<device_id>"`
(`contracts/topics.py`). Every message for one device lands on one
partition.

### 7.3 Ordering guarantees

**Per-device ordering only.** Kafka orders within a partition; the key above
pins one device to one partition, so per-device message order is preserved.
Cross-device ordering is explicitly **not** guaranteed and must not be
assumed by any consumer (a global ordered telemetry stream would require a
single partition, defeating the point of partitioning for throughput).

### 7.4 Replay expectations

- `diep.telemetry` / `diep.events` / `diep.alarms` / `diep.quality.events`:
  standard consumer-group replay from any retained offset within the
  retention window.
- `diep.device.registration` / `diep.device.state`: compacted — a new
  consumer reading from offset 0 reconstructs full current state without
  needing a separate snapshot mechanism (that's what compaction is for).

---

## 8. Reference Documentation Index

- **This document** — MQTT contract (§2), Kafka contract (§7), schema (§3),
  quality model (§4), timestamp rules (§5), versioning (§6), example payload
  (§3).
- `contracts/schema/telemetry.schema.json` — machine-readable JSON Schema.
- `contracts/quality.py`, `contracts/telemetry.py`, `contracts/topics.py` —
  the enforceable source of truth.
- `tests/test_contracts_telemetry.py`, `tests/test_dlms_contract_envelope.py`
  — schema validation, malformed-payload rejection, duplicate handling,
  version compatibility, tenant isolation, timestamp validation, and proof
  that `drivers/dlms` actually emits conformant envelopes.

### Sequence diagram — telemetry, current wiring

```
DLMS meter          drivers/dlms          Runner                 MQTT broker        ingestor              FastAPI/DB
    |                    |                   |                        |                |                      |
    |--OBIS GetRequest-->|                   |                        |                |                      |
    |<--GetResponse------|                   |                        |                |                      |
    |                    |--read_telemetry-->|                        |                |                      |
    |                    |--normalize()----->|                        |                |                      |
    |                    |                   |--build envelope------->|                |                      |
    |                    |                   |  (contracts/telemetry) |                |                      |
    |                    |                   |--publish(base_topic)-->|--diep/meter/--->|                      |
    |                    |                   |                        |   <device_id>  |--from_dict()-------->|
    |                    |                   |                        |                |  (validate, dedup,   |
    |                    |                   |                        |                |   stamp ingestion)   |
    |                    |                   |                        |                |--envelope_to_legacy->|
    |                    |                   |                        |                |   _body() + POST     |
    |                    |                   |                        |                |              /telemetry
```

### Sequence diagram — command/ack (unchanged by this phase)

```
FastAPI --diep.commands(Kafka)--> dispatcher --diep/<domain>/<id>/cmd(MQTT)--> Runner --execute_command--> driver
   ^                                                                                      |
   |<--POST /commands/{id}/ack-------------- dispatcher <--diep/.../ack(MQTT)------------ |
```

### Topic diagram

```
diep/<domain>/<device_id>            (telemetry,  QoS0, not retained)
diep/<domain>/<device_id>/cmd        (commands,   QoS1, not retained)
diep/<domain>/<device_id>/ack        (acks,       QoS1, not retained)
diep/<domain>/<device_id>/alarm      (alarms,     QoS1, not retained)   [new]
diep/<domain>/<device_id>/status     (lifecycle,  QoS1, RETAINED)       [new]
diep/<domain>/<device_id>/heartbeat  (heartbeat,  QoS0, RETAINED)       [new]

diep.commands             (Kafka, 7d)                — existing, wired
diep.telemetry            (Kafka, 7d)                — spec only
diep.events               (Kafka, 30d)                — spec only
diep.alarms               (Kafka, 30d)                — spec only
diep.device.registration  (Kafka, compact)            — spec only
diep.device.state         (Kafka, compact)            — spec only
diep.quality.events       (Kafka, 30d)                — spec only
```

---

## 9. Tests

See `tests/test_contracts_telemetry.py` (contract-module level) and
`tests/test_dlms_contract_envelope.py` (proves `drivers/dlms` actually
publishes conformant envelopes end-to-end against the real simulator).
Coverage: schema validation (structural + JSON Schema cross-check), malformed
payload rejection (missing fields, bad types, bad quality, bad JSON, bad
timestamp_source), duplicate handling (`dedup_key()`), version compatibility
(`is_version_compatible()`, including a real incompatible-MAJOR rejection at
construction), tenant isolation (dedup key and Kafka partition key both
tenant-scoped), and timestamp validation (naive/non-UTC/malformed rejected;
valid ISO8601 UTC variants accepted).

**Environment note:** this shell's `python3` has no `pytest` (a pre-existing
gap — see memory `DLMS test env gap`). Every assertion in both test files was
additionally run manually via plain `python3` against the real
`contracts` package and the real DLMS simulator during this phase, and
passed; the test files themselves still need a properly provisioned
environment or CI to execute as pytest.

---

## 10. Success Criteria — status

| Criterion | Status |
|---|---|
| AMI Ingest publishes it | ✅ `drivers/dlms` (`use_contract_envelope=True`), verified against the live simulator. |
| MDM consumes it unchanged | N/A — MDM not yet built (`PLANNING.md` order: ami-ingest → MDM). Contract is stable for it to build against. |
| OPC UA publishes it unchanged | N/A — OPC UA Phase 0 (discovery) done; Phase 1+ hard-gated on this contract per `PLANNING.md` §1 and `docs/opcua-discovery.md`. |
| CIM maps it unchanged | N/A — last in sequence per `PLANNING.md`. |
| ADMS consumes it unchanged | Existing ADMS code paths are unaffected (ingestor still POSTs the same legacy `TelemetryPayload` shape to FastAPI; the envelope is translated, not propagated, into the DB layer this phase — see §3.1 and the versioning gap noted in §6 for when a consumer needs the envelope directly rather than the flattened legacy view). |
