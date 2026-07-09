"""WP-008 operational network state foundation tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_operational_state import (  # noqa: E402
    InMemoryOperationalStateRepository,
    OperationalEvent,
    OperationalEventProcessor,
    OperationalStateError,
    OperationalStateService,
    OperationalStateValidator,
    StateUpdate,
    StateUpdateEngine,
)
from services.adms_topology_import.mapping import MappedTopology  # noqa: E402
from services.adms_topology_services import InMemoryTopologyRepository  # noqa: E402


def _node(node_id: str, node_type: str) -> dict:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "name": node_id,
        "latitude": 9.0,
        "longitude": 7.0,
        "nominal_kv": 11.0,
        "phases": "ABC",
        "attrs": {"external_id": node_id.replace("adms:node:", ""), "metadata": {}},
    }


def _edge(
    edge_id: str,
    from_node: str,
    to_node: str,
    *,
    edge_type: str = "line",
    switchable: bool = False,
    closed: bool = True,
) -> dict:
    return {
        "edge_id": edge_id,
        "from_node": from_node,
        "to_node": to_node,
        "edge_type": edge_type,
        "is_switchable": switchable,
        "normally_closed": closed,
        "is_closed": closed,
        "rating_kw": 1500.0,
        "phases": "ABC",
        "attrs": {"external_id": edge_id.replace("adms:edge:", ""), "metadata": {}},
    }


def _topology() -> InMemoryTopologyRepository:
    mapped = MappedTopology(
        source_system="adms-supplier-a",
        external_model_id="model-wp-008",
        external_model_version="2026.07.08",
        nodes=(
            _node("adms:node:f1", "feeder"),
            _node("adms:node:a", "bus"),
            _node("adms:node:b", "bus"),
            _node("adms:node:c", "load"),
        ),
        edges=(
            _edge("adms:edge:e1", "adms:node:f1", "adms:node:a"),
            _edge(
                "adms:edge:sw1",
                "adms:node:a",
                "adms:node:b",
                edge_type="switch",
                switchable=True,
            ),
            _edge("adms:edge:e2", "adms:node:b", "adms:node:c"),
        ),
    )
    return InMemoryTopologyRepository.from_mapped_topology(mapped)


def _stack():
    topology = _topology()
    repository = InMemoryOperationalStateRepository()
    validator = OperationalStateValidator(topology)
    engine = StateUpdateEngine(repository, validator)
    service = OperationalStateService(topology, repository)
    return topology, repository, engine, service


def test_repository_applies_current_state_and_records_history():
    _, repository, engine, _ = _stack()
    update = StateUpdate(
        update_id="u-1",
        asset_id="adms:edge:sw1",
        asset_kind="edge",
        sequence=10,
        observed_at="2026-07-08T19:00:00Z",
        actor="operator-a",
        switch_status="open",
        energized=False,
    )

    result = engine.process(update)

    assert result.accepted is True
    assert repository.require_state("adms:edge:sw1", asset_kind="edge").switch_status == "open"
    assert repository.history("adms:edge:sw1")[0].after.sequence == 10


def test_update_engine_suppresses_duplicates_and_rejects_stale_ordering():
    _, repository, engine, _ = _stack()
    update = StateUpdate(
        update_id="u-1",
        asset_id="adms:edge:sw1",
        asset_kind="edge",
        sequence=10,
        observed_at="2026-07-08T19:00:00Z",
        actor="operator-a",
        switch_status="open",
    )

    assert engine.process(update).accepted is True
    duplicate = engine.process(update)
    stale = engine.process(
        StateUpdate(
            update_id="u-2",
            asset_id="adms:edge:sw1",
            asset_kind="edge",
            sequence=9,
            observed_at="2026-07-08T18:59:59Z",
            actor="operator-a",
            switch_status="closed",
        )
    )

    assert duplicate.duplicate is True
    assert stale.accepted is False
    assert stale.reason == "stale_update_sequence"
    assert len(repository.history("adms:edge:sw1")) == 1


def test_operational_state_service_recalculates_feeder_energisation():
    _, _, engine, service = _stack()
    engine.process(
        StateUpdate(
            update_id="u-1",
            asset_id="adms:edge:sw1",
            asset_kind="edge",
            sequence=10,
            observed_at="2026-07-08T19:00:00Z",
            actor="operator-a",
            switch_status="open",
        )
    )

    feeder = service.feeder_energisation("adms:node:f1")

    assert service.connectivity_state("adms:edge:sw1").closed is False
    assert feeder.energized_nodes == ("adms:node:a", "adms:node:f1")
    assert feeder.deenergized_nodes == ("adms:node:b", "adms:node:c")


def test_operational_event_processor_maps_switch_alarm_and_telemetry_events():
    _, repository, engine, service = _stack()
    processor = OperationalEventProcessor(engine)
    results = processor.process_many(
        (
            OperationalEvent(
                event_id="e-2",
                event_type="alarm",
                asset_id="adms:node:c",
                asset_kind="node",
                sequence=20,
                observed_at="2026-07-08T19:01:00Z",
                actor="adms",
                payload={"flags": ["faulted", "manual_hold"]},
                correlation_id="corr-1",
            ),
            OperationalEvent(
                event_id="e-1",
                event_type="switch_operation",
                asset_id="adms:edge:sw1",
                asset_kind="edge",
                sequence=19,
                observed_at="2026-07-08T19:00:30Z",
                actor="operator-a",
                payload={"status": "open"},
                correlation_id="corr-1",
            ),
            OperationalEvent(
                event_id="e-3",
                event_type="telemetry",
                asset_id="adms:node:a",
                asset_kind="node",
                sequence=21,
                observed_at="2026-07-08T19:01:30Z",
                actor="adms",
                payload={"energized": True},
                correlation_id="corr-1",
            ),
        )
    )

    assert [result.event.event_id for result in results] == ["e-1", "e-2", "e-3"]
    assert repository.require_state("adms:node:c", asset_kind="node").available is False
    assert repository.require_state("adms:node:c", asset_kind="node").flags == frozenset(
        {"faulted", "manual_hold"}
    )
    assert service.asset_state("adms:node:a", asset_kind="node").energized is True


def test_consistency_validation_rejects_orphan_and_invalid_switch_state():
    topology = _topology()
    validator = OperationalStateValidator(topology)

    orphan_report = validator.validate_update(
        StateUpdate(
            update_id="u-orphan",
            asset_id="adms:edge:missing",
            asset_kind="edge",
            sequence=1,
            observed_at="2026-07-08T19:00:00Z",
            actor="operator-a",
            switch_status="open",
        )
    )
    invalid_report = validator.validate_update(
        StateUpdate(
            update_id="u-invalid",
            asset_id="adms:edge:e2",
            asset_kind="edge",
            sequence=2,
            observed_at="2026-07-08T19:00:01Z",
            actor="operator-a",
            switch_status="open",
        )
    )

    assert orphan_report.diagnostics[0].reason_code == "orphaned_state"
    assert invalid_report.diagnostics[0].reason_code == "non_switchable_edge_state"


def test_history_replay_reconstructs_prior_operational_state():
    _, repository, engine, _ = _stack()
    updates = (
        StateUpdate(
            update_id="u-1",
            asset_id="adms:edge:sw1",
            asset_kind="edge",
            sequence=10,
            observed_at="2026-07-08T19:00:00Z",
            actor="operator-a",
            switch_status="open",
        ),
        StateUpdate(
            update_id="u-2",
            asset_id="adms:edge:sw1",
            asset_kind="edge",
            sequence=11,
            observed_at="2026-07-08T19:01:00Z",
            actor="operator-a",
            switch_status="closed",
        ),
    )

    engine.process_many(updates)
    replayed = repository.replay_until(10)

    assert repository.require_state("adms:edge:sw1", asset_kind="edge").switch_status == "closed"
    assert replayed.require_state("adms:edge:sw1", asset_kind="edge").switch_status == "open"


def test_invalid_update_raises_deterministic_error():
    _, _, engine, _ = _stack()

    with pytest.raises(OperationalStateError, match="empty_update"):
        engine.process(
            StateUpdate(
                update_id="u-empty",
                asset_id="adms:node:a",
                asset_kind="node",
                sequence=1,
                observed_at="2026-07-08T19:00:00Z",
                actor="operator-a",
            )
        )
