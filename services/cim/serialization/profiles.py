"""Named export profiles -- a `?profile=` query param selects which CIM
object types an export covers. Deliberately simple: a profile is a set of
allowed object-type names; "full" means no restriction. Each entry also
carries a (currently unused) per-class field allowlist slot for future
per-field filtering -- documented as not yet populated in LIMITATIONS.md,
not silently pretended to exist.
"""
from __future__ import annotations

PROFILES: dict[str, dict[str, set[str] | None] | None] = {
    "metering": {
        "EndDevice": None, "Meter": None, "UsagePoint": None, "ServicePoint": None,
        "Customer": None, "Measurement": None, "MeasurementValue": None,
    },
    "network": {
        "ConnectivityNode": None, "Terminal": None, "Transformer": None, "Feeder": None,
    },
    "measurements": {
        "Measurement": None, "MeasurementValue": None,
    },
    "full": None,
}


def object_type_allowed(profile: str, object_type: str) -> bool:
    """True if `object_type` (a CIM class name, e.g. "Meter") is included
    under `profile`."""
    allowed = PROFILES.get(profile)
    if allowed is None:
        return True
    return object_type in allowed
