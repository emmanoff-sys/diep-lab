"""AMI Ingest Phase 4 — contract tests for contracts/telemetry.py.

Covers the spec's "Tests" deliverable: schema validation, malformed payload
rejection, duplicate handling, version compatibility, tenant isolation,
timestamp validation. See AMI_INGEST_PHASE4_CONTRACT.md.

Known environment gap (see memory: DLMS test env gap) — this shell's python3
has no pytest; these are written to house style (tests/test_dlms_driver.py)
and need a properly provisioned environment (or CI) to actually run.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "drivers"))

from contracts import Measurement, Quality, SCHEMA_VERSION, TelemetryEnvelope, is_version_compatible
from contracts.telemetry import ContractValidationError
from contracts.topics import (
    KAFKA_RETENTION, KAFKA_TOPICS, build_ack_topic, build_cmd_topic,
    build_telemetry_topic, partition_key,
)


def _valid_kwargs(**overrides):
    base = dict(
        tenant_id="tenantA",
        site_id="site1",
        device_id="METER001",
        meter_id="METER001",
        timestamp_utc="2026-06-25T12:00:00Z",
        measurements=[Measurement(measurement_type="voltage", unit="V", value=231.0)],
    )
    base.update(overrides)
    return base


# --- schema validation (structural, via contracts/telemetry.py) -----------

def test_valid_envelope_round_trips():
    env = TelemetryEnvelope(**_valid_kwargs())
    again = TelemetryEnvelope.from_json(env.to_json())
    assert again.device_id == "METER001"
    assert again.measurements[0].value == 231.0
    assert again.measurements[0].quality is Quality.GOOD


def test_valid_envelope_matches_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = os.path.join(os.path.dirname(__file__), "..", "contracts", "schema", "telemetry.schema.json")
    with open(schema_path) as f:
        schema = json.load(f)
    env = TelemetryEnvelope(**_valid_kwargs())
    jsonschema.validate(env.to_dict(), schema)


# --- malformed payload rejection -------------------------------------------

@pytest.mark.parametrize("missing", ["tenant_id", "site_id", "device_id", "meter_id"])
def test_missing_required_field_rejected(missing):
    kwargs = _valid_kwargs()
    kwargs[missing] = ""
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope(**kwargs)


def test_empty_measurements_rejected():
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope(**_valid_kwargs(measurements=[]))


def test_non_numeric_value_rejected():
    with pytest.raises(ContractValidationError):
        Measurement(measurement_type="voltage", unit="V", value="not-a-number")


def test_invalid_quality_rejected():
    with pytest.raises(ContractValidationError):
        Measurement(measurement_type="voltage", unit="V", value=1.0, quality="NOT_A_QUALITY")


def test_invalid_timestamp_source_rejected():
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope(**_valid_kwargs(timestamp_source="BOGUS"))


def test_malformed_json_rejected():
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope.from_json("{not valid json")


def test_non_object_json_rejected():
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope.from_json("[1, 2, 3]")


def test_duplicate_measurement_type_within_envelope_rejected():
    kwargs = _valid_kwargs(measurements=[
        Measurement(measurement_type="voltage", unit="V", value=231.0),
        Measurement(measurement_type="voltage", unit="V", value=232.0),
    ])
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope(**kwargs)


# --- duplicate handling (cross-message, via dedup_key) ---------------------

def test_dedup_key_identical_for_identical_reading():
    a = TelemetryEnvelope(**_valid_kwargs())
    b = TelemetryEnvelope(**_valid_kwargs())
    assert a.dedup_key() == b.dedup_key()


def test_dedup_key_differs_on_sequence_number():
    a = TelemetryEnvelope(**_valid_kwargs(sequence_number=0))
    b = TelemetryEnvelope(**_valid_kwargs(sequence_number=1))
    assert a.dedup_key() != b.dedup_key()


def test_dedup_key_differs_on_tenant_even_if_device_id_collides():
    """Tenant isolation: two tenants' devices must never collide in dedup/state
    even if a device_id is accidentally reused across tenants."""
    a = TelemetryEnvelope(**_valid_kwargs(tenant_id="tenantA"))
    b = TelemetryEnvelope(**_valid_kwargs(tenant_id="tenantB"))
    assert a.dedup_key() != b.dedup_key()


# --- version compatibility --------------------------------------------------

@pytest.mark.parametrize("version,expected", [
    (SCHEMA_VERSION, True),
    ("1.0", True),
    ("1.99", True),    # same MAJOR, newer MINOR — additive-only, compatible
    ("2.0", False),    # MAJOR bump — breaking, incompatible
    ("0.9", False),
])
def test_version_compatibility(version, expected):
    assert is_version_compatible(version) is expected


def test_incompatible_major_version_rejected_at_construction():
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope(**_valid_kwargs(schema_version="2.0"))


# --- tenant isolation (topic + partition key level) ------------------------

def test_kafka_partition_key_scoped_by_tenant():
    assert partition_key("tenantA", "METER001") != partition_key("tenantB", "METER001")


def test_kafka_partition_key_requires_tenant_and_device():
    with pytest.raises(ValueError):
        partition_key("", "METER001")


def test_mqtt_topic_builders_are_stable_strings():
    assert build_telemetry_topic("meter", "METER001") == "diep/meter/METER001"
    assert build_cmd_topic("meter", "METER001") == "diep/meter/METER001/cmd"
    assert build_ack_topic("meter", "METER001") == "diep/meter/METER001/ack"


def test_kafka_topic_registry_has_no_duplicate_names():
    names = list(KAFKA_TOPICS.values())
    assert len(names) == len(set(names))
    assert all(name in KAFKA_RETENTION for name in names)


# --- timestamp validation ---------------------------------------------------

@pytest.mark.parametrize("bad_ts", [
    "not-a-timestamp",
    "2026-06-25",                      # date only, not a full timestamp
    "2026-06-25T12:00:00",             # naive — no timezone
    "2026-06-25T12:00:00+05:00",       # not UTC
    "",
])
def test_invalid_timestamp_utc_rejected(bad_ts):
    with pytest.raises(ContractValidationError):
        TelemetryEnvelope(**_valid_kwargs(timestamp_utc=bad_ts))


@pytest.mark.parametrize("good_ts", [
    "2026-06-25T12:00:00Z",
    "2026-06-25T12:00:00+00:00",
    "2026-06-25T12:00:00.123456+00:00",
])
def test_valid_timestamp_utc_accepted(good_ts):
    env = TelemetryEnvelope(**_valid_kwargs(timestamp_utc=good_ts))
    assert env.timestamp_utc == good_ts


def test_ingestion_timestamp_stamped_separately_from_driver():
    """A driver must never set ingestion_timestamp (contract doc §5) — it's
    the ingestor's clock, stamped on receipt."""
    env = TelemetryEnvelope(**_valid_kwargs())
    assert env.ingestion_timestamp is None
    env.stamp_ingestion_time()
    assert env.ingestion_timestamp is not None


# --- estimated/quality cross-layer contract (PLANNING.md §3) ---------------

def test_estimated_quality_forces_estimated_flag_true():
    m = Measurement(measurement_type="power_kw", unit="kW", value=1.0, quality=Quality.ESTIMATED, estimated=False)
    assert m.estimated is True  # quality=ESTIMATED always implies estimated=True, regardless of input


def test_good_quality_does_not_force_estimated():
    m = Measurement(measurement_type="power_kw", unit="kW", value=1.0, quality=Quality.GOOD)
    assert m.estimated is False
