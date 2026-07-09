# OA-073 — Integration Test Harness Specification

**Version:** 1.0.0
**Work Package:** WP-011-01
**Effective Date:** 2026-07-09

---

## 1. Purpose

This document specifies a reusable test framework for all Phase 2 connector
work packages. Connector implementations (WP-011-02 onwards) must use this
harness in their test suites. The harness validates contract compliance,
provides deterministic mock external systems, enables replay testing, and
registers connector tests in the Release 2 classification.

---

## 2. Framework Architecture

```
tests/
  integration_harness/
    __init__.py
    contracts.py        — contract validators (one per canonical contract)
    stubs.py            — deterministic mock external-system stubs
    datasets.py         — canonical test datasets
    replay.py           — recorded-session replay capability
    assertions.py       — connector-specific assertion helpers

services/
  adms_integration_harness/   (future — not part of WP-011-01 implementation)
    __init__.py
    validators.py
    ...
```

> **WP-011-01 scope:** This document specifies the harness design. The harness
> package is not implemented here — it is implemented as part of WP-011-02 or
> as a separate preparatory work package at the Programme Board's discretion.

---

## 3. Contract Validators

Each canonical contract must have a client-side validator function that
connector test suites can call before and after translation.

### 3.1 MappedTopology Validator

```python
def validate_mapped_topology(obj) -> None:
    """Raise AssertionError if obj is not a valid MappedTopology v1.0."""
    assert obj.source_system, "source_system required"
    assert obj.external_model_id, "external_model_id required"
    assert obj.external_model_version, "external_model_version required"
    assert obj.nodes, "at least one node required"
    assert obj.edges, "at least one edge required"
    for node in obj.nodes:
        assert node["node_id"], "node_id required"
        assert node["node_type"] in VALID_NODE_TYPES
        assert -90.0 <= node["latitude"] <= 90.0
        assert -180.0 <= node["longitude"] <= 180.0
        assert node["nominal_kv"] > 0
    for edge in obj.edges:
        assert edge["edge_id"], "edge_id required"
        assert edge["from_node"] != edge["to_node"]
        assert edge["edge_type"] in VALID_EDGE_TYPES
```

### 3.2 OperationalEvent Validator

```python
def validate_operational_event(event) -> None:
    """Raise AssertionError if event is not a valid OperationalEvent v1.0."""
    assert event.event_id, "event_id required"
    assert event.event_type in ALLOWED_EVENT_TYPES
    assert event.asset_id, "asset_id required"
    assert event.asset_kind in ("node", "edge")
    assert event.sequence > 0
    assert event.observed_at, "observed_at required (ISO 8601)"
    assert event.actor, "actor required"
    assert isinstance(event.payload, dict)
    _validate_payload(event.event_type, event.payload)
```

### 3.3 HistoricalEvent Validator

```python
def validate_historical_event(event) -> None:
    """Raise AssertionError if event is not a valid HistoricalEvent v1.0."""
    assert event.asset_id, "asset_id required"
    assert event.kind, "kind required"
    assert event.observed_at, "observed_at required (ISO 8601)"
```

---

## 4. Deterministic Mock External System Stubs

Stubs must be deterministic: given the same input configuration, they produce
the same outputs on every test run. No randomness, no wall-clock use.

### 4.1 SCADA Stub

```python
class ScadaStub:
    """Deterministic SCADA telemetry source for connector testing."""

    def __init__(self, events: tuple[dict, ...]) -> None:
        """events: sequence of raw SCADA messages to emit."""
        self._events = events
        self._index = 0

    def next_message(self) -> dict | None:
        """Return the next SCADA message, or None if exhausted."""
        if self._index >= len(self._events):
            return None
        msg = self._events[self._index]
        self._index += 1
        return msg

    def reset(self) -> None:
        self._index = 0
```

### 4.2 GIS Stub

```python
class GisStub:
    """Deterministic GIS model source for adapter testing."""

    def __init__(self, mapped_topology) -> None:
        self._topology = mapped_topology

    def fetch_model(self) -> object:
        return self._topology
```

### 4.3 OMS Stub

```python
class OmsStub:
    """Deterministic OMS historical event source."""

    def __init__(self, events: tuple) -> None:
        self._events = events

    def fetch_history(self) -> tuple:
        return self._events
```

---

## 5. Canonical Test Datasets

Each connector test suite must include at least the following canonical
datasets. These are shared across all connector packages to enable
cross-connector regression.

### 5.1 Minimal Two-Feeder Dataset

A minimal two-feeder network (mirrors the WP-009 operations fixture) with:
- 2 source nodes (f1, f2);
- 7 nodes total (f1, a, b, c, f2, d, e);
- 6 edges (e1, sw1, e2, tie1, e3, e4);
- 1 normally-open tie (tie1).

This dataset must be used in every connector test that exercises outage
detection downstream of the connector.

### 5.2 Fault Event Dataset

A sequence of `OperationalEvent` objects producing an e1 fault:

```python
FAULT_EVENT = OperationalEvent(
    event_id="test:e1-fault:001",
    event_type="breaker_operation",
    asset_id="e1",
    asset_kind="edge",
    sequence=1,
    observed_at="2026-07-09T20:00:00Z",
    actor="test-connector",
    payload={"status": "open", "available": False},
)
```

### 5.3 Full Topology Dataset

A `MappedTopology` object covering the minimal two-feeder network, derived
from the WP-009 fixture topology. Used in GIS adapter tests.

---

## 6. Replay Capability

The harness must support recording a live session against a real external
system and replaying it deterministically in tests:

```python
class SessionRecorder:
    """Records raw external messages for later deterministic replay."""

    def record(self, message: dict) -> None: ...
    def save(self, path: str) -> None: ...  # JSON Lines format

class SessionReplayer:
    """Replays a recorded session against a connector under test."""

    def __init__(self, path: str) -> None: ...
    def replay(self, connector) -> tuple[dict, ...]: ...
```

Recorded sessions are stored in `tests/integration_harness/recordings/`
as JSON Lines files named `<connector>-<scenario>-<date>.jsonl`. They are
version-controlled alongside the connector work package.

---

## 7. Regression Strategy

Every connector work package must:

1. Pass the 346-test Phase 1 regression suite — no exceptions.
2. Include at minimum:
   - a contract compliance test (using the validators in §3);
   - a translation correctness test (using the canonical dataset in §5);
   - an end-to-end test driving the full path from stub → contract → Phase 1
     ingestion service → outage detection (where applicable);
   - a duplicate-suppression test (sequence ≤ previous → rejected);
   - an untranslatable-message test (connector logs and continues, does not crash).
3. Classify its test files in the Release 2 test classification.
4. Not introduce any new `assert <call>` patterns that would trigger
   CodeQL `py/side-effect-in-assert`.

---

## 8. Acceptance Gate

Before a connector work package may submit its governed PR:

- [ ] Contract validator called on every produced canonical object
- [ ] All five mandatory test categories present (§7.2)
- [ ] Phase 1 regression suite passes (346+ tests)
- [ ] New tests classified in Release 2 classification
- [ ] Ruff, Black, isort, Bandit gates pass on connector package
- [ ] `git diff --check` clean
- [ ] CodeQL clean (including no `py/side-effect-in-assert`)
