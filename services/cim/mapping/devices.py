"""Maps `devices` rows to EndDevice (generic) / Meter (device_type='smartmeter'
specialization). See CIM_MAPPING_GUIDE.md.
"""
from __future__ import annotations

from .. import db, identifiers, topology
from ..models import EndDevice, Meter

_BASE_SELECT = (
    "SELECT device_id, device_type, location, status, site_name, tenant_id FROM devices"
)


def _row_to_kwargs(row: dict) -> dict:
    feeder_id, transformer_id = topology.feeder_and_transformer_for(row["device_id"])
    return dict(
        mRID=identifiers.mrid_for("EndDevice", row["device_id"]),
        name=row["device_id"],
        deviceType=row.get("device_type"),
        status=row.get("status"),
        siteName=row.get("site_name"),
        tenantId=row.get("tenant_id"),
        location=row.get("location"),
        feederMRID=identifiers.mrid_for("Feeder", feeder_id) if feeder_id else None,
        transformerMRID=identifiers.mrid_for("Transformer", transformer_id) if transformer_id else None,
    )


def end_device_from_row(row: dict) -> EndDevice:
    return EndDevice(**_row_to_kwargs(row))


def meter_from_row(row: dict) -> Meter:
    return Meter(**_row_to_kwargs(row))


def list_end_devices(*, tenant_id: str | None, device_type: str | None = None,
                      site_name: str | None = None, limit: int, offset: int) -> list[EndDevice]:
    clauses, params = db.build_filter([
        ("tenant_id = %s", tenant_id),
        ("device_type = %s", device_type),
        ("site_name = %s", site_name),
    ])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(
        f"{_BASE_SELECT} {where} ORDER BY device_id LIMIT %s OFFSET %s",
        params + (limit, offset),
    )
    return [end_device_from_row(r) for r in rows]


def get_end_device(device_id: str, *, tenant_id: str | None) -> EndDevice | None:
    clauses, params = db.build_filter([("device_id = %s", device_id), ("tenant_id = %s", tenant_id)])
    row = db.query_one(f"{_BASE_SELECT} WHERE {' AND '.join(clauses)}", params)
    return end_device_from_row(row) if row else None


def list_meters(*, tenant_id: str | None, site_name: str | None = None,
                 limit: int, offset: int) -> list[Meter]:
    clauses, params = db.build_filter([
        ("tenant_id = %s", tenant_id),
        ("site_name = %s", site_name),
    ])
    extra = f" AND {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(
        f"{_BASE_SELECT} WHERE device_type = 'smartmeter'{extra} ORDER BY device_id LIMIT %s OFFSET %s",
        params + (limit, offset),
    )
    return [meter_from_row(r) for r in rows]


def get_meter(device_id: str, *, tenant_id: str | None) -> Meter | None:
    clauses, params = db.build_filter([("device_id = %s", device_id), ("tenant_id = %s", tenant_id)])
    extra = f" AND {' AND '.join(clauses)}" if clauses else ""
    row = db.query_one(f"{_BASE_SELECT} WHERE device_type = 'smartmeter'{extra}", params)
    return meter_from_row(row) if row else None
