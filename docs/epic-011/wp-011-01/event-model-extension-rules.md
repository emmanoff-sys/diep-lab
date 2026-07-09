# OA-071 — Event Model Extension Rules

**Version:** 1.0.0
**Work Package:** WP-011-01
**Effective Date:** 2026-07-09

---

## 1. Purpose

This document defines the governed process for extending the canonical
contracts defined in OA-070. Extending a contract without following this
process is an unauthorised change to the Phase 1 architecture freeze.

---

## 2. Change Classification

| Change Type | Example | Required Process |
|-------------|---------|-----------------|
| **Non-breaking extension** | Add optional field to `attrs` | Connector implements, no ECR |
| **Non-breaking addition** | Add new optional field to a contract struct | ECR light-touch (single approver) |
| **Breaking addition** | Add new mandatory field | ECR + Programme Board |
| **New event type** | New `event_type` in `OperationalEvent` | ECR + Programme Board |
| **New asset kind** | New `asset_kind` value | ECR + WP-008 engineering change |
| **Breaking removal** | Remove any field or endpoint | ECR + Programme Board + deprecation period |
| **Contract version bump** | Increment `api_version` | Full PAO required |

---

## 3. Non-Breaking Extension (Connector-Only)

A connector may add data inside an existing `attrs` / `payload` dict without
any governance process, provided:

1. The added key is namespaced to the connector (e.g. `"dnp3_quality_flags"`).
2. The Phase 1 ingestion service ignores the unknown key (all Phase 1 services
   do — they are schema-permissive on `attrs` and `payload`).
3. The connector's own test suite validates the extension.
4. The extension is documented in the connector work package's OAR.

---

## 4. ECR Process (Non-Breaking Additions)

For adding a new optional field to a canonical contract struct:

1. Raise an Engineering Change Request (ECR) in the EECR with:
   - the field name, type, and default value;
   - the consuming service(s) and how they will use it;
   - backward compatibility evidence (existing consumers unaffected).
2. Obtain sign-off from the Backend Tech Lead.
3. Add the field to the canonical contract definition with a default of
   `None` or an appropriate empty value.
4. Record the change in the Contract Registry (OA-070 §6) with a patch
   version bump.
5. The full Phase 1 regression suite (346 tests minimum) must pass.
6. The connector work package that first uses the field must classify
   its new test in the Release 2 test classification.

---

## 5. Programme Board Process (Breaking Changes and New Event Types)

For adding a new mandatory field, a new `event_type`, a new `asset_kind`,
or any breaking removal:

1. Raise an Architecture Decision Record (ADR) or ECR with full justification.
2. Submit to the Programme Board for approval.
3. Obtain GOV-004 (or equivalent) sign-off.
4. Record the decision in the EECR with a change record.
5. Implement under a new PAO targeting the affected Phase 1 layer.
6. The affected Phase 1 layer must pass its full test suite after the change.
7. All existing connectors using the affected contract must be updated and
   re-validated before the change can be merged.

---

## 6. New Event Types

Adding a new `event_type` to `OperationalEvent` requires the Programme Board
process (§5) and additionally:

1. Document the new type in OA-070 §3.2 with its allowed `asset_kind` values.
2. Define its payload schema in OA-070 §3.3.
3. Add at least one unit test to `test_adms_operational_state.py` covering
   the new type's mapping behaviour in `OperationalEventProcessor`.
4. Update the traceability test suite for WP-011-01.

---

## 7. New Asset Kinds

Adding a new `asset_kind` (e.g. `"measurement"` for analogue points) requires
the Programme Board process (§5) and additionally:

1. Assess the impact on `OperationalStateValidator` — it validates asset
   references against the topology. A new `asset_kind` that does not map
   to topology nodes or edges requires a WP-008 extension PAO.
2. Update the `OperationalEvent` contract (OA-070 §3.1) to list the new kind.
3. Add topology-level support if the new kind requires it.

---

## 8. Deprecation Policy

When a field or event type is deprecated:

1. Record the deprecation in the EECR with the target removal version.
2. The field remains in the contract for a minimum of **two work packages**
   after the deprecation notice, or until all connectors have migrated,
   whichever is longer.
3. Deprecated fields are marked in the contract specification with
   `[DEPRECATED since vX.Y.Z — use Y instead]`.
4. The field is removed only after Programme Board approval of the removal
   ECR and all connector migrations are merged.

---

## 9. Validation Strategy

Every canonical contract must have an associated validator that connectors
invoke before submission:

| Contract | Validation Function Location |
|----------|------------------------------|
| `MappedTopology` | WP-006 publish endpoint (server-side); connector-side: pending WP-011-01 harness |
| `OperationalEvent` | `OperationalStateValidator.validate(event)` (WP-008, already exists) |
| `HistoricalEvent` | Lightweight field-presence check; pending WP-011-01 harness |
| Operator API v1 | HTTP 422 responses from WP-013-02 FastAPI layer |

The integration test harness (OA-073) provides client-side contract validators
that connectors must use in their test suites.

---

## 10. Contract Version History

| Contract | Version | Date | Change Summary |
|----------|---------|------|----------------|
| MappedTopology | 1.0.0 | 2026-07-08 | Initial — WP-006-08 |
| OperationalEvent | 1.0.0 | 2026-07-09 | Initial — WP-008 |
| HistoricalEvent | 1.0.0 | 2026-07-09 | Initial — WP-010 |
| Operator API | 1.0.0 | 2026-07-09 | Initial — WP-013-02 |
