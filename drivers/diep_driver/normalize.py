"""Canonical telemetry schema shared with the DIEP telemetry ingestor / FastAPI
/telemetry endpoint. Drivers normalize native readings onto these fields so a
real driver and a simulator are interchangeable behind the MQTT contract.
"""
from __future__ import annotations

# Must match TelemetryPayload in fastapi/app.py and the ingestor's CANONICAL_FIELDS.
CANONICAL_FIELDS = (
    "voltage", "current", "power_kw", "frequency",
    "solar_kw", "battery_soc", "grid_import_kw", "grid_export_kw",
)


def _num(value):
    """Coerce to float if numeric (bools excluded), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def normalize_canonical(native: dict, aliases: dict[str, str] | None = None) -> dict:
    """Build a canonical telemetry dict from a native reading.

    - Direct canonical fields are passed through.
    - `aliases` maps native_key -> canonical_key for device-specific names
      (e.g. {"soc": "battery_soc", "output_kw": "solar_kw"}).
    - Missing fields default to 0.0 (the API requires every field).
    """
    out = {field: 0.0 for field in CANONICAL_FIELDS}
    for field in CANONICAL_FIELDS:
        v = _num(native.get(field))
        if v is not None:
            out[field] = v
    for native_key, canonical_key in (aliases or {}).items():
        v = _num(native.get(native_key))
        if v is not None and canonical_key in out:
            out[canonical_key] = v
    return out
