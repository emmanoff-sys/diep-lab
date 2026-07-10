"""WP-011-04 OA-090 — AMI canonical metering translation tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ami_connector import (  # noqa: E402
    AMIEventRejection,
    AMIEventTranslator,
    AMIMessage,
    AMIMeterIdentityMap,
)
from services.scada_connector.harness.contracts import (  # noqa: E402
    validate_operational_event,
)

_METER_MAP = AMIMeterIdentityMap(
    {
        "AMI:METER-C-001": ("c", "node"),
        "AMI:METER-E-001": ("e", "node"),
    }
)
_TRANSLATOR = AMIEventTranslator(_METER_MAP, actor="ami-connector-test")


def _make_message(
    msg_type: str,
    meter_id: str = "AMI:METER-C-001",
    seq: int = 1,
    payload: dict | None = None,
) -> AMIMessage:
    if payload is None:
        if msg_type in ("last_gasp", "restoration", "tamper"):
            payload = {"available": msg_type != "last_gasp"}
        else:
            payload = {"energized": True}
    return AMIMessage(
        message_id=f"{meter_id}:{msg_type}:{seq:03d}",
        meter_id=meter_id,
        message_type=msg_type,
        observed_at=f"2026-07-10T06:{seq:02d}:00Z",
        sequence=seq,
        raw_payload=payload,
    )


def test_last_gasp_translates_to_alarm():
    result = _TRANSLATOR.translate(_make_message("last_gasp", payload={"available": False}))
    assert result.success
    assert result.event.event_type == "alarm"
    assert result.event.payload["available"] is False


def test_restoration_translates_to_alarm_available():
    result = _TRANSLATOR.translate(_make_message("restoration", payload={"available": True}))
    assert result.success
    assert result.event.event_type == "alarm"
    assert result.event.payload["available"] is True


def test_tamper_translates_to_alarm():
    result = _TRANSLATOR.translate(_make_message("tamper", payload={"available": True}))
    assert result.success
    assert result.event.event_type == "alarm"


def test_meter_reading_translates_to_telemetry():
    result = _TRANSLATOR.translate(_make_message("meter_reading", payload={"energized": True}))
    assert result.success
    assert result.event.event_type == "telemetry"
    assert result.event.payload["energized"] is True


def test_power_quality_translates_to_telemetry():
    result = _TRANSLATOR.translate(_make_message("power_quality", payload={"energized": True}))
    assert result.success
    assert result.event.event_type == "telemetry"


def test_diagnostic_translates_to_telemetry():
    result = _TRANSLATOR.translate(_make_message("diagnostic", payload={"energized": True}))
    assert result.success
    assert result.event.event_type == "telemetry"


def test_translated_event_satisfies_canonical_contract():
    result = _TRANSLATOR.translate(_make_message("last_gasp", payload={"available": False}))
    validate_operational_event(result.event)


def test_translated_event_asset_id_from_identity_map():
    result = _TRANSLATOR.translate(_make_message("meter_reading", payload={"energized": True}))
    assert result.event.asset_id == "c"
    assert result.event.asset_kind == "node"


def test_translated_event_actor_embedded_in_event_id():
    result = _TRANSLATOR.translate(_make_message("meter_reading", payload={"energized": True}))
    assert "ami-connector-test" in result.event.event_id


def test_unknown_meter_id_produces_rejection():
    msg = AMIMessage(
        message_id="UNKNOWN:001",
        meter_id="AMI:UNKNOWN-METER",
        message_type="last_gasp",
        observed_at="2026-07-10T06:00:00Z",
        sequence=1,
        raw_payload={"available": False},
    )
    result = _TRANSLATOR.translate(msg)
    assert not result.success
    assert result.event is None
    assert isinstance(result.rejection, AMIEventRejection)
    assert "not in identity map" in result.rejection.reason


def test_unknown_message_type_produces_rejection():
    msg = _make_message("disconnect_command")
    result = _TRANSLATOR.translate(msg)
    assert not result.success
    assert "unknown message_type" in result.rejection.reason


def test_missing_payload_key_produces_rejection():
    msg = AMIMessage(
        message_id="AMI:METER-C-001:LASTGASP:NOKEY",
        meter_id="AMI:METER-C-001",
        message_type="last_gasp",
        observed_at="2026-07-10T06:00:00Z",
        sequence=1,
        raw_payload={},
    )
    result = _TRANSLATOR.translate(msg)
    assert not result.success
    assert "available" in result.rejection.reason


def test_rejection_preserves_meter_id():
    msg = AMIMessage(
        message_id="UNKNOWN:001",
        meter_id="AMI:GHOST-METER",
        message_type="last_gasp",
        observed_at="2026-07-10T06:00:00Z",
        sequence=1,
        raw_payload={"available": False},
    )
    result = _TRANSLATOR.translate(msg)
    assert result.rejection.meter_id == "AMI:GHOST-METER"


def test_translate_many_returns_all_results():
    msgs = tuple(
        _make_message(t, payload=p)
        for t, p in [
            ("last_gasp", {"available": False}),
            ("meter_reading", {"energized": True}),
            ("restoration", {"available": True}),
        ]
    )
    results = _TRANSLATOR.translate_many(msgs)
    assert len(results) == 3
    assert all(r.success for r in results)


def test_translation_is_deterministic():
    msg = _make_message("last_gasp", payload={"available": False})
    r1 = _TRANSLATOR.translate(msg)
    r2 = _TRANSLATOR.translate(msg)
    assert r1.event.event_id == r2.event.event_id
    assert r1.event.event_type == r2.event.event_type


def test_translation_result_fields_on_success():
    result = _TRANSLATOR.translate(_make_message("tamper", payload={"available": True}))
    assert result.success is True
    assert result.event is not None
    assert result.rejection is None


def test_translation_result_fields_on_failure():
    msg = _make_message("disconnect_command")
    result = _TRANSLATOR.translate(msg)
    assert result.success is False
    assert result.event is None
    assert result.rejection is not None


def test_extra_payload_fields_not_included_in_canonical_event():
    msg = _make_message(
        "last_gasp",
        payload={"available": False, "voltage_v": 0.0, "reason": "loss"},
    )
    result = _TRANSLATOR.translate(msg)
    assert result.success
    assert set(result.event.payload.keys()) == {"available"}
