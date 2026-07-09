# OA-069 — Integration Architecture Specification

**Version:** 1.0.0
**Work Package:** WP-011-01
**Effective Date:** 2026-07-09

---

## 1. Governing Principle: Connector-as-Translator

Every external integration is a **translator**, not a platform extension.
A connector has one job: receive a message from an external system, translate
it into the correct Phase 1 canonical contract type, and submit it to the
correct Phase 1 ingestion service. Connectors contain no ADMS business logic.

```
External System
      │
      │  (proprietary protocol)
      ▼
 [Connector]
      │
      │  translate ──► validate ──► submit
      ▼
Phase 1 Canonical Contract Type
      │
      ▼
Phase 1 Ingestion Service (unchanged)
```

---

## 2. Integration Layering

```
┌─────────────────────────────────────────────────────────────────┐
│  External Systems                                                │
│  SCADA │ GIS │ OMS │ AMI │ (future)                            │
└───────────────────────────┬─────────────────────────────────────┘
                             │  proprietary protocols
┌────────────────────────────▼────────────────────────────────────┐
│  Phase 2 — Connector Layer  (EPIC-011)                           │
│  One connector package per external system per protocol          │
│  No business logic. No cross-connector dependencies.             │
│  Produces only canonical contract types.                         │
└───────────────────────────┬─────────────────────────────────────┘
                             │  canonical contracts only
┌────────────────────────────▼────────────────────────────────────┐
│  Phase 1 — Ingestion Surface (frozen, WP-006..013-02)           │
│  MappedTopology publish endpoint (WP-006)                        │
│  OperationalEventProcessor (WP-008)                              │
│  HistoricalEvent list (WP-010)                                   │
│  Operator API v1 (WP-013-02, read-only consumer surface)         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Connector Responsibilities

A connector package MUST:

1. Accept messages from exactly one external system type.
2. Validate the incoming message against the external system's known schema.
3. Map every field deterministically to its canonical contract type.
4. Reject and log (but not crash on) messages that cannot be fully mapped.
5. Submit the contract object to the designated Phase 1 ingestion service.
6. Record the submission result (accepted/rejected) in its own audit log.

A connector package MUST NOT:

1. Call `OutageDetectionService`, `IsolationBoundaryService`, `SwitchingPlanService`,
   or any other Phase 1 analytical service.
2. Read from the `InMemoryTopologyRepository` or `InMemoryOperationalStateRepository`
   to make routing decisions.
3. Issue write-back commands to the external system.
4. Hold mutable shared state across message submissions.
5. Import from another connector package.

---

## 4. Canonical Ingestion Paths

### 4.1 Topology Exchange Path (GIS → WP-006)

```
GIS system
    │  CIM XML / OGC WFS / GeoPackage
    ▼
[GIS Adapter] — transforms → MappedTopology (canonical contract v1.0)
    │
    │  HTTP POST /api/topology/publish (WP-006 endpoint)
    ▼
InMemoryTopologyRepository (WP-007 consumer)
```

The GIS adapter is responsible for:
- fetching the current GIS model export;
- resolving node and edge identifiers to stable `node_id` / `edge_id` values;
- populating all required `MappedTopology` fields;
- calling the WP-006 publish endpoint;
- recording the resulting topology version.

---

### 4.2 Operational Event Path (SCADA / AMI → WP-008)

```
SCADA / AMI
    │  IEC 61850 / DNP3 / IEC 60870-5-104 / AMI REST
    ▼
[Protocol Connector] — translates → OperationalEvent (canonical contract v1.0)
    │
    │  OperationalEventProcessor.process(event)
    ▼
StateUpdateEngine → InMemoryOperationalStateRepository (WP-008)
```

The protocol connector is responsible for:
- maintaining a persistent connection to the external system;
- mapping each incoming device state message to a single `OperationalEvent`;
- assigning a monotonically increasing `sequence` per asset;
- supplying `observed_at` from the external system timestamp (not wall clock);
- supplying its own identifier as `actor`.

---

### 4.3 Historical Correlation Path (OMS → WP-010)

```
OMS
    │  REST / CSV / batch export
    ▼
[OMS Adapter] — transforms → tuple[HistoricalEvent, ...]
    │
    │  OperationalIntelligenceService(view, history=events)
    ▼
FaultLocationAssistanceService (WP-010 consumer)
```

The OMS adapter produces a static or periodically refreshed tuple of
`HistoricalEvent` records. These are injected at `OperationalIntelligenceService`
construction time, not streamed.

---

### 4.4 Operator API Read Path (External Consumers → WP-013-02)

```
External consumer (reporting tool, SCADA display, mobile)
    │  HTTP GET /api/v1/...
    ▼
OperatorApi v1 (WP-013-02, read-only, authenticated)
```

No Phase 2 work is required to expose the existing Operator API to external
read-only consumers — only credentials and network routing. No modifications
to WP-013-02 are authorised unless a future versioned PAO is issued.

---

## 5. Event Flow Diagrams

### 5.1 Live Switch State Update

```
SCADA RTU ──DNP3──► Connector
    normalise ──► OperationalEvent(
                    event_id="dnp3:rtu-07:sw-42:seq-1234",
                    event_type="breaker_operation",
                    asset_id="sw-42",          ← mapped from DNP3 point index
                    asset_kind="edge",
                    sequence=1234,
                    observed_at="2026-07-09T20:00:00Z",
                    actor="dnp3-connector-rtu-07",
                    payload={"status": "open", "available": True}
                  )
    │
    ▼ OperationalEventProcessor.process(event)
    │
    ▼ StateUpdateEngine.apply(event)
    │
    ▼ InMemoryOperationalStateRepository (WP-008)
    │
    ▼ OutageDetectionService detects dark component (WP-009)
    │
    ▼ OperationalIntelligenceService assesses (WP-010)
    │
    ▼ Operator API /api/v1/dashboard shows updated state (WP-013-02)
```

### 5.2 Topology Model Refresh

```
GIS export job ──CIM XML──► GIS Adapter
    parse → map → validate ──► MappedTopology v1.0
    │
    ▼ POST /api/topology/publish (WP-006)
    │
    ▼ InMemoryTopologyRepository updated (WP-007)
    │
    ▼ All analytical layers consume new topology on next call
```

---

## 6. Trust Boundaries

| Boundary | Direction | Control |
|----------|-----------|---------|
| OT network → Connector host | Inbound only | Data diode or one-way gateway; no reverse path |
| Connector host → RE-OS ingestion | Outbound only | Authenticated HTTPS with mTLS client certificate |
| External consumer → Operator API | Inbound read only | Bearer token; GET routes only; 401/403 enforced |
| RE-OS → External system | **Never** | No write-back path exists or shall be created |

---

## 7. Error Handling Strategy

### 7.1 Untranslatable Messages

When a connector receives a message it cannot fully map to a canonical
contract (missing mandatory field, unknown asset reference, schema violation):

1. Log the raw message with a structured error record (timestamp, source,
   error type, raw payload truncated to 1 KB).
2. Increment a connector-scoped rejection counter (observable via a future
   health endpoint).
3. Continue processing the next message without crashing.
4. Do NOT submit a partial contract object to the ingestion service.

### 7.2 Ingestion Service Rejection

When the Phase 1 ingestion service rejects a submitted contract (e.g.
`UpdateResult.accepted is False` due to stale sequence):

1. Log the rejection with the full `UpdateResult` reason.
2. Increment a sequence-error counter.
3. If rejections exceed a configurable threshold within a rolling window,
   the connector must enter a degraded state and alert the health surface.

### 7.3 Connection Loss

Connectors must implement exponential backoff with jitter for reconnection.
State consistency on reconnect (e.g. sequence gap after a DNP3 integrity
scan) is the connector's responsibility to resolve, not the Phase 1 platform's.

---

## 8. Asset Identity Resolution

The most critical mapping challenge in all connectors is resolving external
asset identifiers (DNP3 point index, GIS feeder ID, AMI meter serial number)
to the stable `asset_id` values used by the WP-006 topology model.

**Requirement:** every connector must maintain or consume an asset identity
map: `external_identifier → asset_id`. This map is:
- produced and owned by the integration team (not the Phase 1 platform);
- version-controlled alongside the connector;
- validated against the current `InMemoryTopologyRepository` node and edge
  IDs on connector startup;
- governed as a first-class artefact in the EECR alongside the connector WP.

Connectors must fail fast at startup if the asset identity map references
`asset_id` values not present in the current topology.
