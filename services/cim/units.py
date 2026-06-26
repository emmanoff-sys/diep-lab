"""Canonical-unit -> CIM UnitSymbol/UnitMultiplier mapping.

CIM (IEC 61970 Meas package) expresses a quantity's unit as two separate
enumerations: UnitSymbol (the base unit, e.g. "W", "Hz") and UnitMultiplier
(a scale factor, e.g. "k" for kilo, "none" for 1x) -- rather than a single
combined string like "kW". This mirrors that: CANONICAL_UNITS maps each
canonical unit string this platform actually produces (see
contracts/telemetry.py, services/mdm/units.py) to
(unit_symbol, unit_multiplier, scale_to_base).

unit_symbol values follow UCUM short codes, matching contracts/telemetry.py's
own docstring describing its `unit` field as "UCUM-style short codes" --
this is **spec-shaped, not independently verified** against the official
CIM UnitSymbol RDF/UML enumeration (no access to that artifact here) --
see LIMITATIONS.md.

Deliberately conservative: only the units this platform actually emits
today (see services/mdm/units.py's CANONICAL_UNITS plus
ingestor/telemetry_ingestor.py's CANONICAL_FIELDS/EXTENDED_NUMERIC, which
also includes percentage (battery_soc/soh) and dimensionless ratio
(power_factor)). Anything else raises CimUnitError rather than guessing --
no silent transformations.
"""
from __future__ import annotations


class CimUnitError(ValueError):
    pass


# canonical unit string -> (CIM unit_symbol, CIM unit_multiplier, scale to base unit)
CANONICAL_UNITS: dict[str, tuple[str, str, float]] = {
    "V": ("V", "none", 1.0),
    "A": ("A", "none", 1.0),
    "kW": ("W", "k", 1000.0),
    "Hz": ("Hz", "none", 1.0),
    "kWh": ("Wh", "k", 1000.0),
    "C": ("Cel", "none", 1.0),
    "%": ("PerCent", "none", 1.0),
    "": ("1", "none", 1.0),  # dimensionless ratio (e.g. power_factor)
}

# telemetry measurement_type -> canonical unit string. The ingestor's
# envelope_to_legacy_body() does not persist the original `unit` string
# per row (telemetry.metadata.quality[type] carries only {quality,
# estimated, ...}) -- the canonical columns are already field-name-implies-
# unit by convention, same as services/mdm/units.py's CANONICAL_UNITS.
# CIM infers units from this fixed table, not from stored per-row data,
# since none exists -- documented here and in LIMITATIONS.md, not silently
# assumed.
MEASUREMENT_TYPE_UNITS: dict[str, str] = {
    "voltage": "V",
    "current": "A",
    "power_kw": "kW",
    "frequency": "Hz",
    "solar_kw": "kW",
    "battery_soc": "%",
    "grid_import_kw": "kW",
    "grid_export_kw": "kW",
    "power_factor": "",
    "energy_import_kwh": "kWh",
    "energy_export_kwh": "kWh",
    "temperature": "C",
    "soh": "%",
}


def to_cim_unit(canonical_unit: str) -> tuple[str, str, float]:
    """Returns (unit_symbol, unit_multiplier, scale_to_base) for a known
    canonical unit; raises CimUnitError for anything not in the registry."""
    try:
        return CANONICAL_UNITS[canonical_unit]
    except KeyError:
        raise CimUnitError(f"no CIM unit mapping for canonical unit {canonical_unit!r}") from None


def base_unit_value(value: float, canonical_unit: str) -> float:
    """Converts a value expressed in canonical_unit to the CIM base unit
    (e.g. 2.5 'kW' -> 2500.0 'W'). Raises CimUnitError for unknown units."""
    _, _, scale = to_cim_unit(canonical_unit)
    return value * scale
