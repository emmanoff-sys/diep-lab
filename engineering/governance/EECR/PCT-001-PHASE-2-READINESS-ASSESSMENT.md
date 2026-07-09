# RE-OS ADMS Programme — Phase 2 Readiness Assessment

**Document ID:** PCT-001-PHASE-2-READINESS-ASSESSMENT
**Programme:** RE-OS / DAEP
**Authorisation:** PCT-001
**Effective Date:** 2026-07-09
**Subject:** EPIC-011 — External Utility Integrations

---

## 1. Purpose

This document assesses the programme's readiness to commence Phase 2:
EPIC-011 External Utility Integrations. It reviews integration architecture
needs, candidate external systems, security and trust boundaries, canonical
contract requirements, event model requirements, data ownership, and
operational risks.

---

## 2. Phase 1 Integration Foundation

Phase 1 established the absorbing surfaces for Phase 2 integrations:

| Layer | Entry Point for External Data |
|-------|-------------------------------|
| WP-006 Runtime | `MappedTopology` publish contract — the sole path for external network model data to enter the platform |
| WP-008 State | `OperationalEventProcessor` + `StateUpdateEngine` — the authorised path for live device state events; caller supplies `asset_id`, `asset_kind`, `actor`, and a structured `payload` |
| WP-010 Intelligence | `HistoricalEvent` — typed caller-supplied prior event records for rule-based correlation (fault location, confidence adjustment) |
| WP-013-02 Operator API | Existing `/api/v1` endpoints are read-only aggregation; external consumers (e.g. an EPIC-011 dashboard adapter) can call these without any platform modification |

Phase 2 connectors write into these surfaces. They do not bypass them.

---

## 3. Candidate External Systems

### 3.1 SCADA (Supervisory Control and Data Acquisition)

**Role:** Primary source of live device state (switch positions, breaker
status, availability, analogue measurements).

**Integration need:** A SCADA connector that translates incoming telemetry
and control-status messages into `OperationalEvent` objects and submits them
to the WP-008 `OperationalEventProcessor`. The connector must never originate
a write-back command — the platform is advisory-only.

**Protocol candidates:** IEC 61850 (MMS/GOOSE), DNP3, IEC 60870-5-104,
Modbus TCP. Each requires its own governed connector work package under
EPIC-011.

**Data ownership:** The SCADA master station owns real-time device state.
The RE-OS platform is a consumer, not an authority.

**Security boundary:** SCADA networks are typically air-gapped or on a
separate OT network segment. The connector lives in a DMZ/data-diode-protected
zone; no write path from the RE-OS platform to the SCADA bus is authorised.

---

### 3.2 GIS (Geographic Information System)

**Role:** Primary source of authoritative network topology, asset attributes,
and spatial data.

**Integration need:** A GIS export adapter that produces `MappedTopology`
payloads (the WP-006 `MappedTopology` dataclass contract) from GIS feature
layers. This is the governed path for topology updates; it replaces manual
model imports.

**Protocol candidates:** GIS REST/OGC WFS export, CIM XML/RDF, GeoPackage,
Esri Shapefile. The CIM XML path is already supported by the WP-006 parser
layer and is the preferred canonical format.

**Data ownership:** The GIS system owns the authoritative network model.
The RE-OS platform version-controls a snapshot. Conflict resolution on
concurrent model changes is a governance question, not an engineering one.

**Security boundary:** GIS is typically an enterprise IT system. The adapter
is a one-way, pull-based ETL process with no write-back to GIS.

---

### 3.3 OMS (Outage Management System)

**Role:** Records, tracks, and closes outage tickets; may hold historical
outage event data valuable for fault-location correlation.

**Integration need (inbound):** Historical outage event records exposed to
the WP-010 `HistoricalEvent` interface for correlation confidence. The OMS
is a historical source, not a real-time one.

**Integration need (outbound, future):** Operator recommendations generated
by WP-009/WP-010 could be exported to OMS as advisory outage work orders.
This is explicitly out of Phase 2 scope (requires a bidirectional write path
that does not exist yet).

**Security boundary:** OMS is an IT system. Inbound correlation feeds are
read-only from RE-OS's perspective.

---

### 3.4 AMI (Advanced Metering Infrastructure)

**Role:** Smart meter network providing granular consumption, quality events,
and last-gasp outage signals from the customer network edge.

**Integration need:** AMI outage signals (last-gasp, voltage dip) can be
translated into `OperationalEvent` objects for the WP-008 processor, enriching
the operational picture at the load node level. Meter IDs must be resolved
to topology asset IDs via a metering-to-topology map (a separate data
contract not yet defined).

**Security boundary:** AMI headend systems are enterprise IT. The connector
reads from the AMI event stream and translates; no RE-OS write-back.

---

## 4. Canonical Integration Contract Requirements

Phase 2 connectors must not embed business logic. The contracts defined in
Phase 1 govern what enters the platform:

| Contract | Owner | Phase 2 Obligation |
|----------|-------|--------------------|
| `MappedTopology` | WP-006 | GIS/OMS adapters produce this exactly — no schema divergence |
| `OperationalEvent` | WP-008 | SCADA/AMI connectors produce this exactly — no new event kinds without a WP-008 ECR |
| `HistoricalEvent` | WP-010 | OMS correlation feeds produce this — minimal schema, easily satisfied |
| v1 Operator API envelope | WP-013-02 | External consumers read this — no breaking changes to the v1 contract |

**Recommendation:** WP-011-01 should define and publish these four contracts
as versioned, repository-held integration specifications before any
protocol-specific connector work begins. Contract-first prevents drift.

---

## 5. Event Model Requirements

The WP-008 `OperationalEvent` covers the following kinds today:

| `event_type` | Payload keys | Source |
|---|---|---|
| `breaker_operation` | `status`, `available` | SCADA, AMI |
| `alarm` | `available` | SCADA, SCADA DR |
| `telemetry` | `energized` | SCADA analogue |

Phase 2 connectors will introduce new sources (SCADA DNP3, IEC 61850,
AMI last-gasp, GIS change notification). The `OperationalEvent` schema is
designed to absorb them without modification — the `event_type` and `payload`
fields are open. However:

- A new `event_type` must be documented and reviewed before use.
- A new `payload` key that affects `StateUpdateEngine` behaviour requires
  a WP-008 ECR.
- SCADA analogue telemetry (magnitude, quality flags) may require a new
  `asset_kind` (`measurement`) — needs a governed extension.

---

## 6. Security and Trust Boundaries

| Boundary | Risk | Control |
|----------|------|---------|
| OT/IT network interface (SCADA DMZ) | Lateral movement from IT to OT if connector is compromised | Data diode or one-way gateway; connector has no write-back to SCADA |
| GIS credential exposure | GIS credentials stored in connector config | Use environment-injected secrets; not hardcoded; rotate on schedule |
| AMI event spoofing | Attacker injects false outage signals | Connector authenticates to AMI headend; event integrity verified |
| RE-OS read-only contract | External consumers issuing POST/PATCH via the Operator API | GET-only HTTP surface; enforced structurally; confirmed by CodeQL |
| Confidentiality of network model | Topology data is operationally sensitive | Future: field-level access control on Operator API v2 responses |

---

## 7. Data Ownership Matrix

| Data Domain | Authoritative Source | RE-OS Role |
|-------------|---------------------|------------|
| Network topology | GIS | Versioned consumer (publish via WP-006) |
| Live device state | SCADA | Event consumer (WP-008 state engine) |
| Outage history | OMS | Historical correlation input (WP-010) |
| Customer-to-node map | CIS / AMI headend | Lookup for node customer counts (future) |
| Operator decisions | RE-OS audit trail | Authoritative record (WP-009 OA-042) |
| Recommendations | RE-OS intelligence | Advisory only — no authority to execute |

---

## 8. Operational Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| SCADA connector failure silently stales the operational state | HIGH | Health-check indicator in Operator API dashboard; state age tracking in WP-008 (requires new field — governed extension) |
| GIS model version divergence from live topology | HIGH | Version-lock: WP-006 publish contract records the source model version; operators see model staleness via topology version history endpoint |
| OMS event flood overwhelming historical correlation | MEDIUM | Rate-limit on `HistoricalEvent` ingestion at the connector boundary |
| AMI last-gasp signal mis-attributed to wrong topology node | MEDIUM | Metering-to-topology map must be governed and validated before AMI connector goes live |
| Phase 2 connector introduces business logic duplicating Phase 1 | MEDIUM | Contract-first approach (WP-011-01) enforces separation; connectors produce contract types only |
| Integration tests not representative of live OT environment | LOW | Governed staging acceptance activity before production cutover |

---

## 9. Phase 2 Readiness Verdict

**The programme is READY to commence Phase 2 planning under EPIC-011.**

The Phase 1 platform provides well-defined, stable ingestion surfaces, a
governed operator-facing API, and an established pattern for additive extension.
The key prerequisite before protocol-specific connector work begins is a
canonical contract specification (recommended as WP-011-01) that locks the
four integration contracts and documents the event model extension rules.
