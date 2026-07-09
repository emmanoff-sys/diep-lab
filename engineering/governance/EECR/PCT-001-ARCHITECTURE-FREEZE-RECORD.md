# RE-OS ADMS Programme — Architecture Freeze Record

**Document ID:** PCT-001-ARCHITECTURE-FREEZE-RECORD
**Programme:** RE-OS / DAEP
**Authorisation:** PCT-001 / PAR-001 / GOV-004
**Effective Date:** 2026-07-09
**Baseline:** `develop/v1.1 @ 93e6053901bc0c0eb4fc5fc124c7b569eccd7b85`

---

## 1. Purpose

This record formally freezes the Phase 1 ADMS architecture as the authoritative
engineering baseline. No layer listed below may be redesigned, refactored, or
replaced without a formally approved governance decision (ADR or ECR submitted
to the Programme Board and recorded in the EECR).

---

## 2. Frozen Layers

### Layer 1 — Production ADMS Runtime (`services/adms_topology_import/`)

**Frozen at:** WP-006-08, PR #39, `e923332d`

The production ADMS runtime ingests external network model data through a
governed CIM/IEC 61968 mapping pipeline, validates, persists, and publishes
topology versions. The `MappedTopology` dataclass is the stable contract
consumed by all higher layers. The atomic publish endpoint, version history,
and write-stamp diff semantics are authoritative.

**Constraint:** No parser, mapper, validator, persistence, publish, scheduler,
API, security, or recovery redesign without ECR approval.

---

### Layer 2 — Topology Services (`services/adms_topology_services/`)

**Frozen at:** WP-007, PR #40, `5d079bde`

Provides immutable in-memory network model snapshots, deterministic connectivity
traversal, network query services, feeder tracing, path analysis, outage impact
analysis, and non-destructive switching simulation. `InMemoryTopologyRepository`
and `SOURCE_NODE_TYPES` are stable consumer-facing contracts.

**Constraint:** No redesign of repository, graph engine, tracing, or switching
simulation interfaces without ECR approval.

---

### Layer 3 — Operational Network State (`services/adms_operational_state/`)

**Frozen at:** WP-008, PR #41, `a206df08`

Tracks live operational state for topology assets. The `StateUpdateEngine`
(with validation), `OperationalEventProcessor`, `InMemoryOperationalStateRepository`,
and `OperationalStateService` (connectivity state, device availability, feeder
energisation) are stable contracts. Duplicate suppression and stale-sequence
rejection are protocol invariants.

**Constraint:** No redesign of update semantics, state model, history append-
only contract, or event mapping without ECR approval.

---

### Layer 4 — Operations & Decision Support (`services/adms_operations/`)

**Frozen at:** WP-009, PR #42, `cf297765`

The `OperationalNetworkView` shared traversal keystone and the five service
interfaces (detection, isolation, switching, restoration, advisory) are stable.
Safety rules SR-001..SR-005 are programme policy, not implementation detail.
The `OperationsAuditTrail` append-only record and `DecisionRecord` schema are
authoritative audit contracts.

**Constraint:** No redesign of the shared view, safety rules, or audit trail
schema without ECR approval and Programme Board ruling.

---

### Layer 5 — Operational Intelligence (`services/adms_operational_intelligence/`)

**Frozen at:** WP-010, PR #43, `6d65c5b8`

The `HypotheticalNetworkState` non-destructive overlay, N-1 contingency
analysis, fault location confidence model, rule-based restoration optimisation,
`RuleEngine` (rules as data), decision explanations, and scenario simulation
are stable advisory services. The default rule set (OI-R-001..OI-R-004) is
baseline policy.

**Constraint:** No redesign of the overlay mechanism, rule engine evaluator
contract, or explanation schema without ECR approval.

---

### Layer 6 — Platform Operational Readiness (`docs/adms-operational-readiness/wp-013-01/`)

**Frozen at:** WP-013-01, PR #44, `40a68ea`

The deployment architecture, observability standards, operational runbooks,
resilience validation, security readiness, deployment rehearsal, and
operational readiness assessment documents are accepted as the Phase 1
operational practice baseline. Amendments require a governed documentation
change.

---

### Layer 7 — Operator Situational Awareness (`services/adms_operator_api/`, `services/adms_operator_ui/`)

**Frozen at:** WP-013-02, PR #45, `b55a9c5`

The v1 Operator API envelope contract (`{"api_version": "v1", "view": ...,
"data": ...}`), GET-only route set under `/api/v1`, view model dataclasses,
authentication model, and application shell + workspace structure are the
established Operator Experience Layer. Future operator applications extend
this layer; they do not replace it.

**Constraint:** No breaking change to the v1 envelope or route set without a
versioning decision recorded in the EECR.

---

## 3. Freeze Enforcement

Any proposed change to a frozen layer must:

1. Raise an ADR or ECR with architectural justification.
2. Obtain Programme Board approval.
3. Be recorded in the EECR before implementation commences.
4. Be implemented under a new PAO.
5. Pass the full regression suite including all 346 Phase 1 tests.

---

## 4. What Is Not Frozen

The following are explicitly not frozen and may proceed under new PAOs:

- New additive services above Layer 7 (future operator workspaces, reporting).
- EPIC-011 external integration connectors (new packages, no lower-layer redesign).
- EPIC-012 advanced analytics (new packages consuming Layers 1–5 as-is).
- EPIC-014 digital twin (new packages).
- Production deployment, hosting, and operational acceptance activities.
- Test classification additions for new suites.
- Governance and release-preparation artefacts.
