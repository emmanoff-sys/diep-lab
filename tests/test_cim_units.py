"""services/cim/units.py -- canonical-unit -> CIM UnitSymbol/UnitMultiplier
conversions; unmapped units raise CimUnitError (no silent guessing)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.cim import units


def test_kw_converts_to_watts_with_kilo_multiplier():
    symbol, multiplier, scale = units.to_cim_unit("kW")
    assert symbol == "W" and multiplier == "k" and scale == 1000.0
    assert units.base_unit_value(2.5, "kW") == 2500.0


def test_voltage_amps_hz_have_no_multiplier():
    for unit in ("V", "A", "Hz"):
        symbol, multiplier, scale = units.to_cim_unit(unit)
        assert multiplier == "none" and scale == 1.0


def test_dimensionless_ratio_and_percent_are_mapped_not_skipped():
    symbol, multiplier, scale = units.to_cim_unit("%")
    assert symbol == "PerCent"
    symbol, multiplier, scale = units.to_cim_unit("")
    assert symbol == "1"


def test_unknown_unit_raises_cim_unit_error():
    raised = False
    try:
        units.to_cim_unit("furlongs")
    except units.CimUnitError:
        raised = True
    assert raised, "expected CimUnitError for an unmapped unit"


def test_every_telemetry_measurement_type_has_a_unit_mapping():
    # every measurement_type this platform's telemetry table actually has
    # a column for must resolve to SOME canonical unit (possibly dimensionless)
    expected_types = (
        "voltage", "current", "power_kw", "frequency", "solar_kw", "battery_soc",
        "grid_import_kw", "grid_export_kw", "power_factor", "energy_import_kwh",
        "energy_export_kwh", "temperature", "soh",
    )
    for mtype in expected_types:
        assert mtype in units.MEASUREMENT_TYPE_UNITS, f"{mtype} missing from MEASUREMENT_TYPE_UNITS"
        canonical_unit = units.MEASUREMENT_TYPE_UNITS[mtype]
        units.to_cim_unit(canonical_unit)  # must not raise


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
