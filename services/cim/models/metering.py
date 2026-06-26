"""CIM metering-domain classes: EndDevice, Meter, UsagePoint, ServicePoint,
Customer. See ../../CIM_MAPPING_GUIDE.md for the source-table mapping and
the reasoning behind UsagePoint's deduplication and ServicePoint's role
relative to it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .identified_object import IdentifiedObject


@dataclass(kw_only=True)
class EndDevice(IdentifiedObject):
    """Generic metering/communication endpoint -- maps from any `devices`
    row, regardless of device_type."""
    amrSystem: str | None = None
    isVirtual: bool = False
    timeZoneOffset: str | None = None
    deviceType: str | None = None
    status: str | None = None
    siteName: str | None = None
    tenantId: str | None = None
    location: str | None = None
    feederMRID: str | None = None
    transformerMRID: str | None = None


@dataclass(kw_only=True)
class Meter(EndDevice):
    """Specializes EndDevice -- maps only from `devices` rows where
    device_type='smartmeter'."""
    formNumber: str | None = None


@dataclass(kw_only=True)
class ServicePoint(IdentifiedObject):
    """This platform's own per-customer connection record -- maps 1:1 from
    `service_points`. Distinct from UsagePoint (below): a single physical
    metering point can have several ServicePoints (one per customer sharing
    it -- see the SP-001/002/003 -> ND-METER001 seed data)."""
    customerId: str | None = None
    nodeId: str | None = None
    meterDeviceId: str | None = None
    tenantId: str | None = None


@dataclass(kw_only=True)
class UsagePoint(IdentifiedObject):
    """The CIM-standard point of consumption/production -- deduplicated
    from `service_points` by (node_id, meter_device_id): every
    ServicePoint sharing the same physical node+meter collapses into one
    UsagePoint, with all contributing customers listed in customerIds.
    `synthesized=True` flags a UsagePoint fabricated from a device+site
    fallback because no `service_points` row exists for that device --
    never silently presented as equally authoritative."""
    serviceCategory: str = "electricity"
    isSdp: bool = True
    connectionState: str | None = None
    ratedPower: float | None = None
    nodeId: str | None = None
    meterDeviceId: str | None = None
    customerIds: list[str] = field(default_factory=list)
    tenantId: str | None = None
    synthesized: bool = False


@dataclass(kw_only=True)
class Customer(IdentifiedObject):
    """Maps 1:1 from `customers`."""
    customerName: str | None = None
    priority: str | None = None
    address: str | None = None
    phone: str | None = None
    tenantId: str | None = None
