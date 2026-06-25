"""MDM Validation Engine tests. See AMI_INGEST_PHASE4_CONTRACT.md for the
base contract rules this layers on top of (most rejection cases already
covered by tests/test_contracts_telemetry.py — this file covers the two
checks MDM adds: unit validity and correlation_id UUID format)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.mdm.validation import (
    REASON_CONTRACT_VIOLATION, REASON_INVALID_UNIT, REASON_MALFORMED_CORRELATION_ID, ValidationEngine,
)


def _valid_raw(**overrides):
    base = {
        "schema_version": "1.0", "tenant_id": "tenantA", "site_id": "site1",
        "device_id": "METER001", "meter_id": "METER001",
        "timestamp_utc": "2026-06-25T12:00:00Z", "timestamp_source": "GATEWAY",
        "source_protocol": "dlms", "source_system": "ami-ingest", "sequence_number": 0,
        "ingestion_timestamp": None, "correlation_id": "11111111-1111-1111-1111-111111111111",
        "measurements": [{"measurement_type": "voltage", "unit": "V", "value": 230.0,
                          "quality": "GOOD", "estimated": False}],
    }
    base.update(overrides)
    return base


def test_valid_envelope_accepted():
    result = ValidationEngine().validate(_valid_raw())
    assert result.accepted is True
    assert result.envelope is not None


def test_missing_required_field_rejected_as_contract_violation():
    raw = _valid_raw()
    del raw["tenant_id"]
    result = ValidationEngine().validate(raw)
    assert result.accepted is False
    assert result.reason == REASON_CONTRACT_VIOLATION


def test_invalid_schema_version_rejected():
    result = ValidationEngine().validate(_valid_raw(schema_version="2.0"))
    assert result.accepted is False
    assert result.reason == REASON_CONTRACT_VIOLATION


def test_impossible_timestamp_rejected():
    result = ValidationEngine().validate(_valid_raw(timestamp_utc="not-a-time"))
    assert result.accepted is False
    assert result.reason == REASON_CONTRACT_VIOLATION


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "12345", "", "11111111-1111-1111-1111"])
def test_malformed_correlation_id_rejected(bad_id):
    result = ValidationEngine().validate(_valid_raw(correlation_id=bad_id))
    assert result.accepted is False
    assert result.reason == REASON_MALFORMED_CORRELATION_ID


def test_invalid_unit_rejected():
    raw = _valid_raw(measurements=[
        {"measurement_type": "voltage", "unit": "furlongs", "value": 1.0, "quality": "GOOD", "estimated": False},
    ])
    result = ValidationEngine().validate(raw)
    assert result.accepted is False
    assert result.reason == REASON_INVALID_UNIT
    assert "voltage" in result.invalid_measurement_types


def test_unknown_measurement_type_not_unit_checked():
    """A measurement_type absent from KNOWN_UNITS isn't rejected for its unit
    — only types MDM has an explicit registry entry for are checked."""
    raw = _valid_raw(measurements=[
        {"measurement_type": "totally_custom_field", "unit": "whatever", "value": 1.0,
         "quality": "GOOD", "estimated": False},
    ])
    result = ValidationEngine().validate(raw)
    assert result.accepted is True
