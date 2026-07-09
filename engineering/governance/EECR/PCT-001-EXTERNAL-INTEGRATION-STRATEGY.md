# RE-OS ADMS Programme — External Integration Strategy

**Document ID:** PCT-001-EXTERNAL-INTEGRATION-STRATEGY
**Programme:** RE-OS / DAEP
**Authorisation:** PCT-001
**Effective Date:** 2026-07-09
**Subject:** EPIC-011 — External Utility Integrations

---

## 1. Governing Principle

Phase 2 connectors are **translators**, not platforms. Every external
integration connector has one job: convert an external protocol message into
the correct Phase 1 contract type and submit it to the correct Phase 1
ingestion point. No business logic lives in a connector. No connector bypasses
the Phase 1 contract layer.

---

## 2. Integration Architecture Pattern

```
External System
       │
       │  (proprietary protocol — IEC 61850 / DNP3 / OGC WFS / AMI REST)
       ▼
  [Connector] ─── translates ──► Phase 1 Contract Type
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
       MappedTopology      OperationalEvent      HistoricalEvent
              │                   │
       WP-006 Publisher    WP-008 EventProcessor
```

The connector is stateless and protocol-specific. The platform is stateful
and protocol-agnostic. This boundary must be maintained.

---

## 3. Recommended Work Package Sequence

### Phase 2a — Foundation (EPIC-011)

**WP-011-01: External Integration Architecture and Canonical Contracts**
*(recommended starting point — see separate PAO recommendation)*

Define and publish the canonical integration contracts as governed
specifications. No protocol-specific connector may commence without a
WP-011-01-approved contract baseline.

**WP-011-02: SCADA Connector Framework** *(after WP-011-01)*

A protocol-agnostic SCADA connector base that translates device state
messages into `OperationalEvent` objects. Delivers adapters for one
protocol (recommended: IEC 61850 MMS, as the most common in modern
grid automation). DNP3 and IEC 60870-5-104 adapters follow in
subsequent work packages.

**WP-011-03: GIS Topology Adapter** *(parallel to WP-011-02, after WP-011-01)*

An adapter that pulls from GIS (CIM XML preferred; OGC WFS fallback),
transforms to `MappedTopology`, and submits to the WP-006 publish
endpoint. Includes model version reconciliation and change-detection logic.

**WP-011-04: OMS Historical Correlation Feed** *(after WP-011-01)*

Read-only OMS integration producing `HistoricalEvent` records for the
WP-010 fault location service. Low complexity; high value for confidence
scoring.

**WP-011-05: AMI Last-Gasp Integration** *(after WP-011-03, requires metering-to-topology map)*

AMI outage signal translation to `OperationalEvent`. Depends on a
governed metering-to-topology mapping asset, which must be defined and
validated before WP-011-05 can commence.

### Phase 2b — Integration Testing and Acceptance (EPIC-011)

**WP-011-06: Integration Testing Suite**

End-to-end integration tests against simulated external system stubs
(not live OT systems). Validates the full path from external event to
operator recommendation for each connector type.

**WP-011-07: Staging Acceptance**

Governed acceptance activity against real external systems in a
staging environment. Prerequisite for production cutover.

---

## 4. Security Architecture Decisions Required

The following security decisions must be resolved in WP-011-01 before
any connector implementation:

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Connector credential management | Env-injected secrets / vault / K8s secrets | Vault or K8s secrets; never hardcoded |
| OT/IT network boundary | Data diode / DMZ proxy / VPN | Data diode for SCADA; DMZ for GIS/OMS/AMI |
| Event integrity | Unsigned / HMAC / mTLS | mTLS from SCADA connector to RE-OS event ingestion endpoint |
| Operator API external exposure | Internal only / authenticated external | Authenticated external via API gateway (Phase 2b gate) |

---

## 5. Non-Negotiable Constraints

These carry over from the Phase 1 architecture freeze and apply to all Phase 2 work:

1. **No write-back.** Connectors submit events and topology; they never
   issue commands back to external systems. Switching execution is
   explicitly not authorised.
2. **No business logic in connectors.** Detection, isolation, switching
   safety, and restoration ranking remain in WP-009/WP-010.
3. **No Phase 1 redesign.** If a connector requirement cannot be met by
   the existing Phase 1 contracts, the correct response is to raise an
   ECR against the relevant layer — not to modify the connector to
   work around the contract.
4. **Contract-first.** WP-011-01 must be complete and its contracts
   accepted before any protocol-specific connector work begins.
5. **Full regression required.** Every Phase 2 work package must pass
   the 346-test Phase 1 regression suite plus its own suite. No Phase 1
   regression is acceptable at any merge gate.
