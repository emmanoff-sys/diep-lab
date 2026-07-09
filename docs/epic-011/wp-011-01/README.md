# WP-011-01 — External Integration Architecture and Canonical Contracts

**Programme:** RE-OS / DAEP
**EPIC:** EPIC-011 — External Utility Integrations
**Work Package:** WP-011-01
**Authorisation:** PAO-018
**Baseline:** `develop/v1.1 @ 93e6053`

---

## Purpose

This package defines the architectural contracts and governing rules that
all Phase 2 external integration connectors must satisfy. It is the
mandatory gate before any connector implementation work package commences.

## Deliverables

| Document | Objective | Description |
|----------|-----------|-------------|
| [integration-architecture.md](integration-architecture.md) | OA-069 | Overall integration architecture, layering, ingestion paths, event flows, trust boundaries |
| [canonical-contracts.md](canonical-contracts.md) | OA-070 | Versioned canonical contracts for topology, operational events, historical events, and Operator API v1 |
| [event-model-extension-rules.md](event-model-extension-rules.md) | OA-071 | Governance for extending event models: version evolution, compatibility, deprecation, change process |
| [integration-security-architecture.md](integration-security-architecture.md) | OA-072 | Authentication, authorisation, secret management, OT/IT boundary, audit requirements |
| [integration-test-harness-specification.md](integration-test-harness-specification.md) | OA-073 | Reusable test framework specification for all future connectors |
| [final-architecture-validation.md](final-architecture-validation.md) | OA-074 | Validation record confirming completeness and internal consistency |

## Usage Gate

No EPIC-011 connector work package (WP-011-02 onwards) may be authorised
until WP-011-01 is merged and formally closed.

All connector implementations shall cite the version of each canonical
contract they implement and be regression-tested against the contract
validation test harness defined in OA-073.
