# OA-070 — Canonical Contract Specifications

**Version:** 1.0.0
**Work Package:** WP-011-01
**Effective Date:** 2026-07-09

---

## 1. Overview

This document defines the four canonical contracts that all Phase 2 external
integration connectors must produce or consume. Each contract is versioned,
validated, and enforced by the integration test harness (OA-073).

Modifying a canonical contract requires following the Event Model Extension
Rules (OA-071) and obtaining Programme Board approval.

---

## 2. Contract 1 — MappedTopology (Topology Exchange)

**Version:** 1.0.0
**Ingestion point:** WP-006 publish endpoint (`POST /api/topology/publish`)
**Python type:** `services.adms_topology_import.mapping.MappedTopology`

### 2.1 Mandatory Fields

| Field | Type | Validation | Notes |
|-------|------|-----------|-------|
| `source_system` | `str` | Non-empty; max 128 chars | Identifies the producing GIS / model source |
| `external_model_id` | `str` | Non-empty; max 256 chars | External unique model identifier |
| `external_model_version` | `str` | Non-empty; max 128 chars | External version (ISO 8601 date or semver) |
| `nodes` | `tuple[dict]` | At least 1 node | See Node sub-schema |
| `edges` | `tuple[dict]` | At least 1 edge | See Edge sub-schema |

### 2.2 Node Sub-Schema

| Field | Type | Required | Validation |
|-------|------|----------|-----------|
| `node_id` | `str` | Yes | Non-empty; unique within model; stable across versions |
| `node_type` | `str` | Yes | One of: `feeder`, `substation`, `bus`, `switch`, `load`, `meter`, `junction` |
| `name` | `str\|None` | No | Human-readable label |
| `latitude` | `float` | Yes | WGS84 decimal degrees, -90..90 |
| `longitude` | `float` | Yes | WGS84 decimal degrees, -180..180 |
| `nominal_kv` | `float` | Yes | Positive; nominal voltage in kV |
| `phases` | `str` | Yes | `A`, `B`, `C`, `AB`, `AC`, `BC`, or `ABC` |
| `attrs` | `dict` | Yes | May be empty `{}`; extension point for non-standard fields |

### 2.3 Edge Sub-Schema

| Field | Type | Required | Validation |
|-------|------|----------|-----------|
| `edge_id` | `str` | Yes | Non-empty; unique within model; stable across versions |
| `from_node` | `str` | Yes | Must reference an existing `node_id` |
| `to_node` | `str` | Yes | Must reference an existing `node_id`; `from_node ≠ to_node` |
| `edge_type` | `str` | Yes | One of: `line`, `cable`, `switch`, `breaker`, `transformer`, `fuse`, `recloser` |
| `is_switchable` | `bool` | Yes | True if the device can be remotely or manually operated |
| `normally_closed` | `bool` | Yes | Normal (design) position |
| `is_closed` | `bool` | Yes | Actual position in this model snapshot |
| `rating_kw` | `float\|None` | No | Thermal rating in kW; None if unrated |
| `phases` | `str` | Yes | `A`, `B`, `C`, `AB`, `AC`, `BC`, or `ABC` |
| `attrs` | `dict` | Yes | May be empty `{}`; extension point |

### 2.4 Versioning Policy

- `external_model_version` must increase monotonically per `source_system`.
- The WP-006 publish endpoint rejects versions older than or equal to the
  currently published version for the same source system.
- Connectors must not publish a version unless the model has genuinely changed.

### 2.5 Backward Compatibility

The `attrs` dict is the approved extension mechanism. Connectors may add
non-standard fields inside `attrs` without changing the contract version.
Adding a new mandatory top-level field or removing an existing one requires
a contract version bump and an ECR.

---

## 3. Contract 2 — OperationalEvent (Operational Events)

**Version:** 1.0.0
**Ingestion point:** `services.adms_operational_state.OperationalEventProcessor.process(event)`
**Python type:** `services.adms_operational_state.OperationalEvent`

### 3.1 Mandatory Fields

| Field | Type | Validation |
|-------|------|-----------|
| `event_id` | `str` | Non-empty; unique per actor; used for duplicate detection |
| `event_type` | `str` | See §3.2 Allowed Event Types |
| `asset_id` | `str` | Must match a `node_id` or `edge_id` in the current topology |
| `asset_kind` | `str` | `"node"` or `"edge"` |
| `sequence` | `int` | Positive integer; monotonically increasing per (`actor`, `asset_id`) |
| `observed_at` | `str` | ISO 8601 UTC timestamp; from external system, not connector clock |
| `actor` | `str` | Identifies the connector instance producing this event |
| `payload` | `dict` | See §3.3 Payload Schemas by Event Type |

### 3.2 Allowed Event Types (v1.0.0)

| `event_type` | Description | Allowed `asset_kind` |
|---|---|---|
| `breaker_operation` | Breaker or switch position change | `edge` |
| `alarm` | Device availability alarm | `node` or `edge` |
| `telemetry` | Analogue measurement update | `node` or `edge` |

Connectors MUST NOT use undocumented `event_type` values. Adding a new
`event_type` requires following the Event Model Extension Rules (OA-071).

### 3.3 Payload Schemas by Event Type

**`breaker_operation`**

| Key | Type | Required | Validation |
|-----|------|----------|-----------|
| `status` | `str` | Yes | `"open"` or `"closed"` |
| `available` | `bool` | Yes | Whether the device is operable |

**`alarm`**

| Key | Type | Required | Validation |
|-----|------|----------|-----------|
| `available` | `bool` | Yes | False when the alarm indicates device failure |

**`telemetry`**

| Key | Type | Required | Validation |
|-----|------|----------|-----------|
| `energized` | `bool` | Yes | Derived from analogue measurement (e.g. voltage > threshold) |

### 3.4 Sequence Semantics

- `sequence` values must increase per (`actor`, `asset_id`) pair.
- The `StateUpdateEngine` rejects events with a sequence ≤ the most recently
  accepted sequence for the same (`actor`, `asset_id`) — this is a protocol
  invariant, not a business rule.
- On connector restart after a gap, the connector must resume with a sequence
  greater than the last submitted value. The recommended approach is to use
  the source system's own sequence number if available, or an incrementing
  counter persisted by the connector.

### 3.5 Asset Identity Requirement

`asset_id` must match an `edge_id` or `node_id` in the current topology
snapshot held by the WP-008 `OperationalStateValidator`. Events referencing
unknown assets will be rejected. See OA-069 §8 for the asset identity mapping
requirement.

---

## 4. Contract 3 — HistoricalEvent (Correlation Feed)

**Version:** 1.0.0
**Ingestion point:** Constructor argument to `services.adms_operational_intelligence.OperationalIntelligenceService(view, history=events)`
**Python type:** `services.adms_operational_intelligence.HistoricalEvent`

### 4.1 Fields

| Field | Type | Required | Validation |
|-------|------|----------|-----------|
| `asset_id` | `str` | Yes | Must match an `edge_id` in the current topology |
| `kind` | `str` | Yes | Describes the event type; free-form string from the OMS vocabulary |
| `observed_at` | `str` | Yes | ISO 8601 UTC timestamp of the historical event |

### 4.2 Usage Notes

- `HistoricalEvent` records are passed as a static tuple; they are not streamed
  in real-time. The OMS adapter refreshes this tuple periodically (recommended:
  no more frequently than the GIS model refresh cycle).
- The fault location service uses these records to increase confidence scores
  for candidate fault segments. A longer, denser history improves correlation.
- `kind` values are OMS-vocabulary strings. The Phase 1 service does not
  interpret `kind` — it uses only `asset_id` (for matching) and `observed_at`
  (for display in evidence). Connectors may use any meaningful string.

### 4.3 Versioning Policy

This contract is intentionally minimal. Fields will not be removed in v1.x.
Additional optional fields may be added in patch versions without requiring
connector changes.

---

## 5. Contract 4 — Operator API v1 (External Read-Only Consumers)

**Version:** 1.0.0
**Endpoint base:** `GET /api/v1/...`
**Produced by:** `services.adms_operator_api.OperatorApi`

### 5.1 Envelope Schema

All Operator API responses share this envelope:

```json
{
  "api_version": "v1",
  "view": "<view-name>",
  "data": { ... }
}
```

External consumers MUST check `api_version` before processing `data`. A
response with `api_version != "v1"` is from a future version and must not
be processed by a v1 consumer.

### 5.2 Available Endpoints

| Endpoint | View Name | Description |
|----------|-----------|-------------|
| `GET /api/v1/dashboard` | `dashboard` | Platform status, service health, active outages, indicators |
| `GET /api/v1/network` | `network` | Feeders, nodes, edges with live operational state |
| `GET /api/v1/assets/search?q=<query>` | `asset-search` | Asset search results |
| `GET /api/v1/assets/{asset_id}` | `asset-state` | Single asset state panel |
| `GET /api/v1/topology/{node_id}` | `topology-explorer` | Node neighbourhood |
| `GET /api/v1/recommendations` | `recommendations` | Active outage recommendations with strategies and explanations |
| `GET /api/v1/history` | `history` | Audit records with optional filters |
| `GET /api/v1/history/recommendations` | `recommendation-history` | Recommendation records only |
| `GET /api/v1/history/{record_id}/trace` | `record-trace` | Transitive audit trace |
| `GET /api/v1/timeline` | `timeline` | Merged audit + state event timeline |

### 5.3 Authentication

All requests must carry `Authorization: Bearer <token>`. A missing or
unrecognised token returns HTTP 401. A token without a read role returns
HTTP 403.

### 5.4 Backward Compatibility

- No field will be removed from a `v1` response in a patch or minor version.
- Fields may be added; consumers must ignore unknown fields.
- A breaking change requires a new API version (`v2`) and a separately
  governed migration path.
- External consumers must not POST, PUT, PATCH, or DELETE to any endpoint.
  The server will return HTTP 405 for mutating methods.

---

## 6. Contract Registry

| Contract | Version | Python Type | Introduced |
|----------|---------|-------------|-----------|
| MappedTopology | 1.0.0 | `adms_topology_import.mapping.MappedTopology` | WP-006-08 |
| OperationalEvent | 1.0.0 | `adms_operational_state.OperationalEvent` | WP-008 |
| HistoricalEvent | 1.0.0 | `adms_operational_intelligence.HistoricalEvent` | WP-010 |
| Operator API v1 | 1.0.0 | `adms_operator_api.OperatorApi` | WP-013-02 |
