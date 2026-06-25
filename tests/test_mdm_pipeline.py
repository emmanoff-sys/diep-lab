"""MDM pipeline integration tests — covers the "MQTT publication" and
"estimated/measured propagation" test areas end-to-end (the actual paho
publish call isn't exercised here — that needs a real broker — but the
published topic/payload the pipeline hands to mqtt_io.py is fully verified,
which is everything mqtt_io.client.publish() does with it)."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.mdm.enrichment import DeviceMetadataEnricher
from services.mdm.pipeline import MdmPipeline

FAKE_DEVICES = {"METER001": {"tenant_id": "tenantA", "site_name": "Abuja Site A", "device_type": "meter"}}
FAKE_GRID_NODES = {
    "METER001": {"node_id": "MTR-01", "node_type": "meter", "parent_id": "TX-01"},
    "TX-01": {"node_id": "TX-01", "node_type": "transformer", "parent_id": "FDR-01"},
    "FDR-01": {"node_id": "FDR-01", "node_type": "feeder", "parent_id": None},
}


def _pipeline():
    enricher = DeviceMetadataEnricher(
        device_row_fetcher=lambda did: FAKE_DEVICES.get(did),
        grid_node_fetcher=lambda nid: FAKE_GRID_NODES.get(nid),
    )
    return MdmPipeline(enricher=enricher)


def _raw(**overrides):
    base = {
        "schema_version": "1.0", "tenant_id": "tenantA", "site_id": "Abuja Site A",
        "device_id": "METER001", "meter_id": "METER001", "timestamp_utc": "2026-06-25T12:55:00Z",
        "timestamp_source": "GATEWAY", "source_protocol": "dlms", "source_system": "ami-ingest",
        "sequence_number": 0, "ingestion_timestamp": None,
        "correlation_id": "11111111-1111-1111-1111-111111111111",
        "measurements": [
            {"measurement_type": "voltage", "unit": "V", "value": 230.0, "quality": "GOOD", "estimated": False},
        ],
    }
    base.update(overrides)
    return base


def test_valid_envelope_published_to_trusted_topic():
    result = _pipeline().process(_raw(), domain="meter")
    assert result.accepted is True
    assert result.topic == "diep/meter/METER001/trusted"


def test_invalid_envelope_not_published():
    raw = _raw()
    del raw["tenant_id"]
    result = _pipeline().process(raw, domain="meter")
    assert result.accepted is False
    assert result.topic is None


def test_duplicate_not_published_on_second_call():
    pipeline = _pipeline()
    raw = _raw()
    first = pipeline.process(raw, domain="meter")
    second = pipeline.process(raw, domain="meter")
    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "duplicate"


def test_canonical_schema_fields_unchanged_in_trusted_output():
    """Per the spec: "Do not modify the canonical schema." Every field
    TelemetryEnvelope.to_dict() produces must still be present, unrenamed."""
    result = _pipeline().process(_raw(), domain="meter")
    for field in ("schema_version", "tenant_id", "site_id", "device_id", "meter_id",
                  "timestamp_utc", "timestamp_source", "source_protocol", "source_system",
                  "sequence_number", "correlation_id", "measurements"):
        assert field in result.payload, f"missing canonical field: {field}"


def test_mdm_metadata_is_additive_not_replacing_canonical_fields():
    result = _pipeline().process(_raw(), domain="meter")
    assert "mdm" in result.payload
    assert set(result.payload["mdm"].keys()) == {
        "processed_at", "device_metadata", "quality_transitions",
        "unit_conversions", "gap_events", "timestamp_assessment",
    }


def test_estimated_propagates_through_to_trusted_output():
    raw = _raw(measurements=[
        {"measurement_type": "power_kw", "unit": "kW", "value": 1.0, "quality": "ESTIMATED", "estimated": True},
    ])
    result = _pipeline().process(raw, domain="meter")
    m = result.payload["measurements"][0]
    assert m["quality"] == "ESTIMATED"
    assert m["estimated"] is True


def test_estimation_source_documented_via_quality_value_itself():
    """Spec: "document the estimation source." The quality flag IS the
    documented source/reason (e.g. ESTIMATED vs SUBSTITUTED carry different
    provenance) — MDM does not invent a second, separate provenance field."""
    raw = _raw(measurements=[
        {"measurement_type": "power_kw", "unit": "kW", "value": 1.0, "quality": "SUBSTITUTED", "estimated": True},
    ])
    result = _pipeline().process(raw, domain="meter")
    assert result.payload["measurements"][0]["quality"] == "SUBSTITUTED"
    assert result.payload["mdm"]["quality_transitions"] == []  # untouched — driver-assigned, never overwritten


def test_unit_conversion_recorded_in_mdm_metadata():
    raw = _raw(measurements=[
        {"measurement_type": "power_kw", "unit": "W", "value": 1500.0, "quality": "GOOD", "estimated": False},
    ])
    result = _pipeline().process(raw, domain="meter")
    assert result.payload["measurements"][0]["unit"] == "kW"
    assert result.payload["measurements"][0]["value"] == 1.5
    conv = result.payload["mdm"]["unit_conversions"][0]
    assert conv["original_unit"] == "W"
    assert conv["original_value"] == 1500.0


def test_device_metadata_enrichment_present_in_trusted_output():
    result = _pipeline().process(_raw(), domain="meter")
    meta = result.payload["mdm"]["device_metadata"]
    assert meta["tenant_id"] == "tenantA"
    assert meta["feeder_id"] == "FDR-01"
    assert meta["transformer_id"] == "TX-01"


def test_gap_event_recorded_on_second_reading_after_long_gap():
    pipeline = _pipeline()
    pipeline.gap_detector.default_interval_s = 5
    pipeline.gap_detector.tolerance_multiplier = 2.0
    pipeline.process(_raw(timestamp_utc="2026-06-25T12:55:00Z"), domain="meter")
    result = pipeline.process(_raw(
        timestamp_utc="2026-06-25T12:56:30Z",  # 90s later, way past 10s tolerance
        sequence_number=1,
        correlation_id="22222222-2222-2222-2222-222222222222",
    ), domain="meter")
    assert len(result.payload["mdm"]["gap_events"]) == 1


def test_processing_latency_does_not_crash_without_prometheus_client():
    """Smoke test for the no-op metrics fallback (prometheus_client isn't
    installed in this dev shell — see memory: DLMS test env gap)."""
    result = _pipeline().process(_raw(), domain="meter")
    assert result.accepted is True
