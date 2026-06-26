"""services/cim/mapping/measurements.py -- the "no information loss"
module. Every value/quality/estimated/timestamp/correlation_id must
round-trip byte-for-byte from the source telemetry row's metadata."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import db as cim_db
from services.cim.mapping import measurements as mapping_measurements

_TELEMETRY_ROW = {
    "time": "2026-06-25T23:05:26.701346+00:00",
    "device_id": "SIT-METER-001",
    "voltage": 220.0, "current": None, "power_kw": None, "frequency": None,
    "solar_kw": None, "battery_soc": None, "grid_import_kw": None, "grid_export_kw": None,
    "power_factor": None, "energy_import_kwh": None, "energy_export_kwh": None,
    "temperature": None, "soh": None,
    "metadata": {
        "quality": {"voltage": {"quality": "GOOD", "estimated": False}},
        "correlation_id": "abc-123", "tenant_id": "sit-tenant",
    },
}

_KW_ROW = dict(_TELEMETRY_ROW, power_kw=2.5, metadata={
    "quality": {"power_kw": {"quality": "ESTIMATED", "estimated": True}},
    "correlation_id": "xyz-789", "tenant_id": "sit-tenant",
})


def _patch(query_all):
    orig = cim_db.query_all
    cim_db.query_all = query_all

    def restore():
        cim_db.query_all = orig
    return restore


def test_measurement_value_preserves_value_quality_and_correlation_id():
    mv = mapping_measurements.measurement_value_from_row(_TELEMETRY_ROW, "voltage", {"SIT-METER-001": "sit-tenant"})
    assert mv.rawValue == 220.0
    assert mv.value == 220.0  # V has scale 1.0 -- no conversion should occur
    assert mv.quality == "GOOD"
    assert mv.estimated is False
    assert mv.sourceCorrelationId == "abc-123"
    assert mv.tenantId == "sit-tenant"
    assert mv.unitSymbol == "V"


def test_measurement_value_returns_none_when_no_quality_entry_for_that_type():
    """frequency wasn't in this row's metadata.quality -- must not
    fabricate a reading from the (always-0.0-defaulted) column."""
    mv = mapping_measurements.measurement_value_from_row(_TELEMETRY_ROW, "frequency", {})
    assert mv is None


def test_measurement_value_converts_kw_to_cim_base_unit_watts():
    mv = mapping_measurements.measurement_value_from_row(_KW_ROW, "power_kw", {})
    assert mv.rawValue == 2.5
    assert mv.rawUnit == "kW"
    assert mv.value == 2500.0
    assert mv.unitSymbol == "W"
    assert mv.unitMultiplier == "k"


def test_measurement_value_preserves_estimated_and_non_good_quality():
    mv = mapping_measurements.measurement_value_from_row(_KW_ROW, "power_kw", {})
    assert mv.estimated is True
    assert mv.quality == "ESTIMATED"


def test_measurement_value_mrid_is_deterministic():
    mv1 = mapping_measurements.measurement_value_from_row(_TELEMETRY_ROW, "voltage", {})
    mv2 = mapping_measurements.measurement_value_from_row(_TELEMETRY_ROW, "voltage", {})
    assert mv1.mRID == mv2.mRID


def test_list_measurements_returns_one_definition_per_device_and_type():
    fake_rows = [
        {"device_id": "SIT-METER-001", "measurement_type": "voltage"},
        {"device_id": "SIT-METER-001", "measurement_type": "current"},
    ]
    restore = _patch(lambda sql, params=(): fake_rows)
    try:
        result = mapping_measurements.list_measurements(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert len(result) == 2
    assert {m.measurementType for m in result} == {"voltage", "current"}


def test_list_measurement_values_end_to_end_preserves_everything():
    def fake_query_all(sql, params=()):
        if "ANY(%s)" in sql:
            return [{"device_id": "SIT-METER-001", "tenant_id": "sit-tenant"}]
        return [_TELEMETRY_ROW]
    restore = _patch(fake_query_all)
    try:
        result = mapping_measurements.list_measurement_values(tenant_id=None, limit=10, offset=0)
    finally:
        restore()
    assert len(result) == 1
    mv = result[0]
    assert mv.value == 220.0
    assert mv.quality == "GOOD"
    assert mv.tenantId == "sit-tenant"
    assert mv.sourceCorrelationId == "abc-123"


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
