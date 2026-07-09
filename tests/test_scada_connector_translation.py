"""WP-011-02 OA-076 — canonical event translation tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _scada_connector_fixtures import asset_map  # noqa: E402

from services.scada_connector import (  # noqa: E402
    AssetIdentityMap,
    SCADAConnectorError,
    SCADAEventTranslator,
    SCADAMessage,
)
from services.scada_connector.harness.contracts import validate_operational_event  # noqa: E402
from services.scada_connector.harness.datasets import (  # noqa: E402
    CANONICAL_ASSET_MAP,
    CANONICAL_FAULT_EVENT,
    make_scada_messages,
)


def _translator() -> SCADAEventTranslator:
    return SCADAEventTranslator(asset_map(), actor="test-connector")


def test_fault_event_translates_to_canonical_breaker_operation():
    result = _translator().translate(CANONICAL_FAULT_EVENT)
    assert result.success
    assert result.event is not None
    event = result.event
    validate_operational_event(event)
    assert event.event_type == "breaker_operation"
    assert event.asset_id == "e1"
    assert event.asset_kind == "edge"
    assert event.payload == {"status": "open", "available": False}
    assert event.observed_at == CANONICAL_FAULT_EVENT.observed_at
    assert event.actor == "test-connector"
    assert event.sequence == 1


def test_event_id_prefixed_with_actor():
    result = _translator().translate(CANONICAL_FAULT_EVENT)
    assert result.event.event_id.startswith("test-connector:")
    assert CANONICAL_FAULT_EVENT.message_id in result.event.event_id


def test_alarm_message_translates_correctly():
    msg = SCADAMessage(
        message_id="RTU-01:FEEDER-F1:002",
        external_asset_id="RTU-01:FEEDER-F1",
        message_type="alarm",
        observed_at="2026-07-09T20:01:00Z",
        sequence=2,
        raw_payload={"available": False},
    )
    result = _translator().translate(msg)
    assert result.success
    validate_operational_event(result.event)
    assert result.event.event_type == "alarm"
    assert result.event.asset_id == "f1"
    assert result.event.asset_kind == "node"


def test_telemetry_message_translates_correctly():
    msg = SCADAMessage(
        message_id="RTU-01:FEEDER-F1:003",
        external_asset_id="RTU-01:FEEDER-F1",
        message_type="measurement",
        observed_at="2026-07-09T20:02:00Z",
        sequence=3,
        raw_payload={"energized": True},
    )
    result = _translator().translate(msg)
    assert result.success
    validate_operational_event(result.event)
    assert result.event.event_type == "telemetry"


def test_unknown_external_asset_id_rejected():
    msg = SCADAMessage(
        message_id="RTU-99:CB-UNKNOWN:001",
        external_asset_id="RTU-99:CB-UNKNOWN",
        message_type="status_change",
        observed_at="2026-07-09T20:00:00Z",
        sequence=1,
        raw_payload={"status": "open", "available": False},
    )
    result = _translator().translate(msg)
    assert not result.success
    assert result.event is None
    assert "identity map" in result.rejection_reason


def test_unknown_message_type_rejected():
    msg = SCADAMessage(
        message_id="RTU-01:CB-E1:001",
        external_asset_id="RTU-01:CB-E1",
        message_type="heartbeat",  # not in canonical types
        observed_at="2026-07-09T20:00:00Z",
        sequence=1,
        raw_payload={},
    )
    result = _translator().translate(msg)
    assert not result.success
    assert "unknown message_type" in result.rejection_reason


def test_missing_payload_keys_rejected():
    msg = SCADAMessage(
        message_id="RTU-01:CB-E1:001",
        external_asset_id="RTU-01:CB-E1",
        message_type="status_change",
        observed_at="2026-07-09T20:00:00Z",
        sequence=1,
        raw_payload={"status": "open"},  # missing 'available'
    )
    result = _translator().translate(msg)
    assert not result.success
    assert "available" in result.rejection_reason


def test_asset_identity_map_validates_on_construction():
    import pytest

    with pytest.raises(SCADAConnectorError):
        AssetIdentityMap(
            {"EXT-ZZ": ("nonexistent-asset", "edge")}, known_asset_ids=frozenset({"e1"})
        )


def test_translate_many_preserves_order():
    messages = make_scada_messages(
        ("RTU-01:CB-E1", "status_change", 1, {"status": "open", "available": False}),
        ("RTU-01:CB-SW1", "status_change", 2, {"status": "closed", "available": True}),
    )
    results = _translator().translate_many(messages)
    assert len(results) == 2
    assert results[0].event.asset_id == "e1"
    assert results[1].event.asset_id == "sw1"


def test_translation_is_deterministic():
    t1 = _translator()
    t2 = _translator()
    r1 = t1.translate(CANONICAL_FAULT_EVENT)
    r2 = t2.translate(CANONICAL_FAULT_EVENT)
    assert r1.event == r2.event
