"""CIM measurement-domain classes: Measurement, MeasurementValue, Asset.
MeasurementValue is the "no information loss" class -- see
mapping/measurements.py for how quality/estimated/unit/timestamp/
correlation_id are all carried through from the canonical contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from .identified_object import IdentifiedObject


@dataclass(kw_only=True)
class Measurement(IdentifiedObject):
    """The definition of what is measured (a (device, measurement_type)
    pair) -- not a specific reading. See MeasurementValue for that."""
    measurementType: str | None = None
    unitSymbol: str | None = None
    unitMultiplier: str | None = None
    deviceMRID: str | None = None
    tenantId: str | None = None


@dataclass(kw_only=True)
class MeasurementValue(IdentifiedObject):
    """One actual reading. Carries both the CIM-base-unit value (`value`,
    `unitSymbol`, `unitMultiplier`) and the original canonical-unit value
    (`rawValue`, `rawUnit`) side by side -- converting for CIM must not
    discard the source representation. `quality`/`estimated` are the exact
    strings/booleans from contracts.Quality, never re-interpreted.
    `sourceCorrelationId` is the traceability link back to the canonical
    TelemetryEnvelope this reading came from."""
    measurementMRID: str | None = None
    deviceMRID: str | None = None
    value: float | None = None
    unitSymbol: str | None = None
    unitMultiplier: str | None = None
    rawValue: float | None = None
    rawUnit: str | None = None
    timeStamp: str | None = None
    quality: str | None = None
    estimated: bool = False
    tenantId: str | None = None
    sourceCorrelationId: str | None = None


@dataclass(kw_only=True)
class Asset(IdentifiedObject):
    """Physical equipment with ratings -- maps from `der_assets` only
    (battery/solar/ev_charger/microgrid). Smartmeters and other device
    types have no Asset record in this mapping -- a documented gap, not a
    silently-sparse result; see SUPPORTED_OBJECTS.md."""
    assetType: str | None = None
    ratedKw: float | None = None
    ratedKwh: float | None = None
    controllable: bool | None = None
    vppGroup: str | None = None
    nodeId: str | None = None
    tenantId: str | None = None
