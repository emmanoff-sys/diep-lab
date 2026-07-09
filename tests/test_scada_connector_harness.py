"""WP-011-02 OA-079 — integration test harness tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_operational_intelligence import HistoricalEvent  # noqa: E402
from services.scada_connector.harness import (  # noqa: E402
    CANONICAL_FAULT_EVENT,
    TWO_FEEDER_TOPOLOGY,
    GisStub,
    OmsStub,
    ScadaStub,
    SessionRecorder,
    SessionReplayer,
    make_scada_messages,
    validate_historical_event,
    validate_mapped_topology,
    validate_operational_event,
)


def test_canonical_two_feeder_topology_passes_contract_validator():
    validate_mapped_topology(TWO_FEEDER_TOPOLOGY)
    assert len(TWO_FEEDER_TOPOLOGY.nodes) == 7
    assert len(TWO_FEEDER_TOPOLOGY.edges) == 6


def test_canonical_fault_event_passes_contract_validator_after_translation():
    from _scada_connector_fixtures import connector_stack

    _, _, translator, _, _ = connector_stack()
    result = translator.translate(CANONICAL_FAULT_EVENT)
    validate_operational_event(result.event)


def test_historical_event_validator():
    event = HistoricalEvent(asset_id="e1", kind="breaker_trip", observed_at="2026-07-09T20:00:00Z")
    validate_historical_event(event)
    with pytest.raises(AssertionError):
        validate_historical_event(HistoricalEvent(asset_id="", kind="trip", observed_at="t"))


def test_scada_stub_emits_messages_in_order():
    raw_messages = (
        {"message_id": "m-001", "seq": 1},
        {"message_id": "m-002", "seq": 2},
    )
    stub = ScadaStub(raw_messages)
    assert stub.remaining == 2
    first = stub.next_message()
    assert first["message_id"] == "m-001"
    assert stub.remaining == 1
    stub.next_message()
    assert stub.exhausted
    assert stub.next_message() is None


def test_scada_stub_resets():
    stub = ScadaStub(({"x": 1},))
    stub.next_message()
    assert stub.exhausted
    stub.reset()
    assert not stub.exhausted


def test_gis_stub_returns_topology():
    stub = GisStub(TWO_FEEDER_TOPOLOGY)
    assert stub.fetch_model() is TWO_FEEDER_TOPOLOGY


def test_oms_stub_returns_history():
    events = (HistoricalEvent("e1", "trip", "2026-07-09T20:00:00Z"),)
    stub = OmsStub(events)
    assert stub.fetch_history() is events


def test_session_recorder_and_replayer():
    recorder = SessionRecorder()
    recorder.record({"id": "m-001"})
    recorder.record({"id": "m-002"})
    assert recorder.count == 2
    messages = recorder.messages()
    replayer = SessionReplayer.from_messages(messages)
    assert replayer.count == 2
    replayed = replayer.replay(recorder)
    assert len(replayed) == 2
    assert replayed[0]["id"] == "m-001"


def test_replay_is_deterministic():
    messages = ({"id": "m-001"}, {"id": "m-002"})
    r1 = SessionReplayer.from_messages(messages)
    r2 = SessionReplayer.from_messages(messages)
    rec = SessionRecorder()
    assert r1.replay(rec) == r2.replay(rec)


def test_make_scada_messages_helper():
    messages = make_scada_messages(
        ("RTU-01:CB-E1", "status_change", 1, {"status": "open", "available": False}),
        ("RTU-01:CB-SW1", "alarm", 2, {"available": True}),
    )
    assert len(messages) == 2
    assert messages[0].external_asset_id == "RTU-01:CB-E1"
    assert messages[1].message_type == "alarm"
