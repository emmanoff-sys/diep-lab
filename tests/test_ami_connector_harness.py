"""WP-011-04 OA-093 — AMI replay and test harness integration tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ami_connector import AMIEventTranslator, AMIMeterIdentityMap  # noqa: E402
from services.ami_connector.harness import (  # noqa: E402
    AMI_CANONICAL_BATCH,
    AMI_CANONICAL_METER_MAP,
    AMI_LAST_GASP_EVENT,
    AMI_METER_READING_EVENT,
    AMI_RESTORATION_EVENT,
    AMI_TAMPER_EVENT,
    AmiStub,
)
from services.scada_connector.harness.contracts import (  # noqa: E402
    validate_operational_event,
)
from services.scada_connector.harness.replay import SessionRecorder, SessionReplayer  # noqa: E402


def _translator() -> AMIEventTranslator:
    m = AMIMeterIdentityMap(AMI_CANONICAL_METER_MAP)
    return AMIEventTranslator(m, actor="ami-harness-test")


def test_ami_stub_from_messages_round_trips():
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    assert stub.remaining == 4
    event = stub.next_event()
    assert event is not None
    assert event["meter_id"] == AMI_LAST_GASP_EVENT.meter_id


def test_ami_stub_exhausts_cleanly():
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    for _ in range(4):
        stub.next_event()
    assert stub.exhausted
    assert stub.next_event() is None


def test_ami_stub_resets_deterministically():
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    stub.next_event()
    stub.reset()
    assert stub.remaining == 4
    assert not stub.exhausted


def test_last_gasp_event_translates_to_alarm_available_false():
    result = _translator().translate(AMI_LAST_GASP_EVENT)
    assert result.success
    assert result.event.event_type == "alarm"
    assert result.event.payload["available"] is False


def test_restoration_event_translates_to_alarm_available_true():
    result = _translator().translate(AMI_RESTORATION_EVENT)
    assert result.success
    assert result.event.payload["available"] is True


def test_meter_reading_event_translates_to_telemetry():
    result = _translator().translate(AMI_METER_READING_EVENT)
    assert result.success
    assert result.event.event_type == "telemetry"
    assert result.event.payload["energized"] is True


def test_tamper_event_translates_to_alarm():
    result = _translator().translate(AMI_TAMPER_EVENT)
    assert result.success
    assert result.event.event_type == "alarm"
    assert result.event.payload["available"] is True


def test_all_canonical_batch_events_satisfy_contract():
    t = _translator()
    for msg in AMI_CANONICAL_BATCH:
        result = t.translate(msg)
        assert result.success, f"translation failed for {msg.message_id}: {result.rejection}"
        validate_operational_event(result.event)


def test_canonical_meter_map_covers_all_batch_meters():
    batch_meter_ids = frozenset(m.meter_id for m in AMI_CANONICAL_BATCH)
    assert batch_meter_ids.issubset(set(AMI_CANONICAL_METER_MAP))


def test_session_recorder_captures_stub_events():
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    recorder = SessionRecorder()
    while not stub.exhausted:
        evt = stub.next_event()
        if evt:
            recorder.record(evt)
    assert recorder.count == 4


def test_session_replayer_from_messages_replays_deterministically():
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    events = []
    while not stub.exhausted:
        e = stub.next_event()
        if e:
            events.append(e)
    replayer = SessionReplayer.from_messages(tuple(events))
    assert replayer.count == 4
    messages = replayer.messages
    assert messages[0]["meter_id"] == AMI_LAST_GASP_EVENT.meter_id


def test_replay_produces_identical_translation_results():
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    t = _translator()
    first_run = []
    while not stub.exhausted:
        raw = stub.next_event()
        if raw:
            from services.ami_connector.translation import AMIMessage

            msg = AMIMessage(
                message_id=raw["message_id"],
                meter_id=raw["meter_id"],
                message_type=raw["message_type"],
                observed_at=raw["observed_at"],
                sequence=raw["sequence"],
                raw_payload=raw["raw_payload"],
            )
            first_run.append(t.translate(msg))
    stub.reset()
    second_run = []
    while not stub.exhausted:
        raw = stub.next_event()
        if raw:
            from services.ami_connector.translation import AMIMessage

            msg = AMIMessage(
                message_id=raw["message_id"],
                meter_id=raw["meter_id"],
                message_type=raw["message_type"],
                observed_at=raw["observed_at"],
                sequence=raw["sequence"],
                raw_payload=raw["raw_payload"],
            )
            second_run.append(t.translate(msg))
    for r1, r2 in zip(first_run, second_run, strict=True):
        assert r1.event.event_id == r2.event.event_id
        assert r1.event.event_type == r2.event.event_type
