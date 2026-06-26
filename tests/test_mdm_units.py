"""MDM Unit Normalization tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import Measurement
from services.mdm.units import UnitNormalizer


def test_already_canonical_unit_is_a_noop():
    m = Measurement(measurement_type="voltage", unit="V", value=230.0)
    new, record = UnitNormalizer().normalize(m)
    assert new is m
    assert record is None


def test_wh_to_kwh():
    m = Measurement(measurement_type="energy_import_kwh", unit="Wh", value=1500.0)
    new, record = UnitNormalizer().normalize(m)
    assert new.unit == "kWh"
    assert new.value == 1.5
    assert record.original_unit == "Wh"
    assert record.original_value == 1500.0
    assert record.canonical_unit == "kWh"
    assert record.canonical_value == 1.5


def test_mwh_to_kwh():
    m = Measurement(measurement_type="energy_export_kwh", unit="MWh", value=2.0)
    new, _ = UnitNormalizer().normalize(m)
    assert new.unit == "kWh"
    assert new.value == 2000.0


def test_w_to_kw():
    m = Measurement(measurement_type="power_kw", unit="W", value=1200.0)
    new, _ = UnitNormalizer().normalize(m)
    assert new.unit == "kW"
    assert new.value == 1.2


def test_kv_to_v():
    m = Measurement(measurement_type="voltage", unit="kV", value=0.4)
    new, _ = UnitNormalizer().normalize(m)
    assert new.unit == "V"
    assert new.value == 400.0


def test_fahrenheit_to_celsius():
    m = Measurement(measurement_type="temperature", unit="F", value=98.6)
    new, _ = UnitNormalizer().normalize(m)
    assert new.unit == "C"
    assert round(new.value, 2) == 37.0


def test_kelvin_to_celsius():
    m = Measurement(measurement_type="temperature", unit="K", value=300.0)
    new, _ = UnitNormalizer().normalize(m)
    assert new.unit == "C"
    assert round(new.value, 2) == 26.85


def test_unknown_measurement_type_passes_through_unchanged():
    m = Measurement(measurement_type="totally_custom", unit="widgets", value=5.0)
    new, record = UnitNormalizer().normalize(m)
    assert new is m
    assert record is None


def test_original_value_always_recoverable_from_record():
    m = Measurement(measurement_type="energy_import_kwh", unit="Wh", value=2500.0)
    new, record = UnitNormalizer().normalize(m)
    # round-trip: record always carries enough to reconstruct the original
    recovered = record.original_value
    assert recovered == 2500.0
    assert new.value != recovered  # the measurement itself was actually converted
