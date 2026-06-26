"""MDM Unit Normalization.

Converts each measurement to its measurement_type's canonical unit (the unit
drivers/dlms already publishes today — V/A/kW/Hz — so DLMS readings pass
through this stage as a no-op; the conversion table exists for the next
driver that doesn't). The original unit+value are always preserved in the
returned ConversionRecord — see pipeline.py for where that lands in the
trusted output's additive `mdm` metadata block (contracts/telemetry.py is not
modified to carry this; see MDM_DESIGN.md §3 for why).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from contracts import Measurement

CANONICAL_UNITS = {
    "voltage": "V",
    "current": "A",
    "power_kw": "kW",
    "frequency": "Hz",
    "active_power": "kW",
    "energy_import_kwh": "kWh",
    "energy_export_kwh": "kWh",
    "temperature": "C",
}

# (measurement_type, from_unit) -> (factor to multiply value by to reach the
# canonical unit). Only entries that actually need conversion; a unit already
# matching CANONICAL_UNITS needs no entry (normalize() is a no-op for it).
_CONVERSIONS: dict[tuple[str, str], float] = {
    ("voltage", "kV"): 1000.0,
    ("current", "mA"): 0.001,
    ("power_kw", "W"): 0.001,
    ("power_kw", "MW"): 1000.0,
    ("active_power", "W"): 0.001,
    ("active_power", "MW"): 1000.0,
    ("energy_import_kwh", "Wh"): 0.001,
    ("energy_import_kwh", "MWh"): 1000.0,
    ("energy_export_kwh", "Wh"): 0.001,
    ("energy_export_kwh", "MWh"): 1000.0,
    # temperature (F, K) is affine, not multiplicative — handled as a special
    # case in normalize() rather than a factor here.
}


@dataclass(frozen=True)
class ConversionRecord:
    measurement_type: str
    original_unit: str
    original_value: float
    canonical_unit: str
    canonical_value: float


class UnitNormalizer:
    def normalize(self, measurement: Measurement) -> tuple[Measurement, ConversionRecord | None]:
        canonical_unit = CANONICAL_UNITS.get(measurement.measurement_type)
        if canonical_unit is None or measurement.unit == canonical_unit:
            return measurement, None  # unknown type, or already canonical — no-op

        key = (measurement.measurement_type, measurement.unit)
        if measurement.measurement_type == "temperature" and measurement.unit in ("F", "K"):
            canonical_value = (
                (measurement.value - 32.0) * 5.0 / 9.0 if measurement.unit == "F"
                else measurement.value - 273.15
            )
        elif key in _CONVERSIONS:
            canonical_value = measurement.value * _CONVERSIONS[key]
        else:
            # Unit not in the conversion table for this measurement_type —
            # leave untouched rather than guess. The quality/validation
            # engines, not this one, are responsible for rejecting it.
            return measurement, None

        record = ConversionRecord(
            measurement_type=measurement.measurement_type,
            original_unit=measurement.unit,
            original_value=measurement.value,
            canonical_unit=canonical_unit,
            canonical_value=canonical_value,
        )
        converted = replace(measurement, unit=canonical_unit, value=canonical_value)
        return converted, record
