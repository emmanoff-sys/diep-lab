"""CIM information model -- 12 dataclasses (plus the shared IdentifiedObject
base) corresponding to the 12 classes this sprint's deliverable list names.
Every CIM-standard attribute choice here is **spec-shaped, not
independently verified** against the official IEC 61968/61970 UML/RDF/XSD
artifacts (no access to them in this environment) -- see ../LIMITATIONS.md
and the repo-wide precedent (drivers/dlms/VALIDATION.md,
services/opcua/VALIDATION.md) for the same discipline applied elsewhere.
"""
from __future__ import annotations

from .identified_object import IdentifiedObject
from .measurement import Asset, Measurement, MeasurementValue
from .metering import Customer, EndDevice, Meter, ServicePoint, UsagePoint
from .network import ConnectivityNode, Feeder, Terminal, Transformer

__all__ = [
    "IdentifiedObject",
    "EndDevice",
    "Meter",
    "UsagePoint",
    "ServicePoint",
    "Customer",
    "ConnectivityNode",
    "Terminal",
    "Transformer",
    "Feeder",
    "Measurement",
    "MeasurementValue",
    "Asset",
]
