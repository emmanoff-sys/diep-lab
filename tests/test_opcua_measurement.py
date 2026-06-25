"""Tests for services/opcua/measurement.py — pure stdlib."""
from datetime import datetime, timezone

from services.opcua.measurement import MeasurementSink, build_measurement


def test_good_value_is_valid():
    m = build_measurement(
        server_name="plant1", node_id="ns=2;s=X", measurement_name="battery_soc",
        value=42.5, data_type="float", status_code="Good",
        source_timestamp=datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc),
        server_timestamp=datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 6, 25, 12, 0, 1, tzinfo=timezone.utc),
    )
    assert m.valid is True
    assert m.invalid_reason is None
    assert m.source_timestamp == "2026-06-25T12:00:00Z"


def test_bad_status_code_is_invalid():
    m = build_measurement(
        server_name="p", node_id="n", measurement_name="x", value=1.0, data_type="float",
        status_code="Bad_NodeIdUnknown", source_timestamp=None, server_timestamp=None,
    )
    assert m.valid is False
    assert "status_code" in m.invalid_reason


def test_null_value_is_invalid():
    m = build_measurement(
        server_name="p", node_id="n", measurement_name="x", value=None, data_type="NoneType",
        status_code="Good", source_timestamp=None, server_timestamp=None,
    )
    assert m.valid is False
    assert m.invalid_reason == "null_value"


def test_nan_value_is_invalid():
    m = build_measurement(
        server_name="p", node_id="n", measurement_name="x", value=float("nan"), data_type="float",
        status_code="Good", source_timestamp=None, server_timestamp=None,
    )
    assert m.valid is False
    assert m.invalid_reason == "non_finite_value"


def test_non_numeric_good_value_is_valid():
    m = build_measurement(
        server_name="p", node_id="n", measurement_name="x", value="ON", data_type="str",
        status_code="Good", source_timestamp=None, server_timestamp=None,
    )
    assert m.valid is True


def test_sink_emit_and_latest():
    sink = MeasurementSink(history_size=3)
    for v in (1.0, 2.0, 3.0, 4.0):
        m = build_measurement(server_name="p1", node_id="n", measurement_name="soc", value=v,
                               data_type="float", status_code="Good", source_timestamp=None, server_timestamp=None)
        sink.emit(m)
    assert sink.latest()["p1/soc"]["value"] == 4.0
    assert len(sink.history("p1", "soc")) == 3  # bounded by history_size
    assert [m.value for m in sink.history("p1", "soc")] == [2.0, 3.0, 4.0]


def test_sink_tracks_multiple_keys_independently():
    sink = MeasurementSink()
    m1 = build_measurement(server_name="p1", node_id="n1", measurement_name="soc", value=1.0,
                            data_type="float", status_code="Good", source_timestamp=None, server_timestamp=None)
    m2 = build_measurement(server_name="p2", node_id="n2", measurement_name="soc", value=2.0,
                            data_type="float", status_code="Good", source_timestamp=None, server_timestamp=None)
    sink.emit(m1)
    sink.emit(m2)
    latest = sink.latest()
    assert latest["p1/soc"]["value"] == 1.0
    assert latest["p2/soc"]["value"] == 2.0
