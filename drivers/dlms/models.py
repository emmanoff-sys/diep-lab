"""OBIS code map + DLMS/COSEM constants for the DLMS meter driver.

OBIS codes follow IEC 62056-61 (A.B.C.D.E.F). Default smart-meter profile:
    1.0.32.7.0.255  voltage   (V)
    1.0.31.7.0.255  current   (A)
    1.0.1.7.0.255   active power (kW; signed: + import)
    1.0.14.7.0.255  frequency (Hz)
Logical-name (LN) referencing is used; value attribute ordinal = 2.

⚠️ See dlms/protocol.py VALIDATION CAVEAT — wire encoding is a minimal subset
not yet validated against a real meter.
"""
from __future__ import annotations

# field name -> OBIS logical name
OBIS = {
    "voltage": "1.0.32.7.0.255",
    "current": "1.0.31.7.0.255",
    "power_kw": "1.0.1.7.0.255",
    "frequency": "1.0.14.7.0.255",
}

# reverse lookup (OBIS -> field) for the simulator
FIELD_BY_OBIS = {v: k for k, v in OBIS.items()}

# Default simulator measurement magnitudes.
SIM_DEFAULTS = {
    "voltage": 230.0,
    "current": 5.0,
    "power_kw": 1.0,
    "frequency": 50.0,
}
