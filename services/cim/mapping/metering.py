"""Maps `customers`/`service_points` (and, for the UsagePoint fallback,
`devices`) to Customer, ServicePoint, UsagePoint.

UsagePoint deduplication: the seed data has 3 customers (SP-001/002/003)
sharing one physical node+meter (ND-METER001/METER001) -- 3 ServicePoints
but one real point of delivery. UsagePoint keys on (node_id,
meter_device_id); every ServicePoint sharing that pair collapses into one
UsagePoint, with all contributing customers listed in customerIds. A
service_points row where BOTH node_id and meter_device_id are NULL gets its
own UsagePoint (keyed by service_point_id) rather than being silently
merged with other such rows under a shared NULL key (Postgres GROUP BY
would treat NULL=NULL as one group; deliberately avoided here, done in
Python instead). Devices with no service_points row at all get a
synthesized fallback UsagePoint, explicitly flagged.
"""
from __future__ import annotations

from .. import db, identifiers
from ..models import Customer, ServicePoint, UsagePoint

_CUSTOMER_SELECT = "SELECT customer_id, name, address, phone, priority, tenant_id FROM customers"
_SP_SELECT = "SELECT service_point_id, customer_id, node_id, meter_device_id, tenant_id FROM service_points"


def customer_from_row(row: dict) -> Customer:
    return Customer(
        mRID=identifiers.mrid_for("Customer", row["customer_id"]),
        name=row.get("name") or row["customer_id"],
        customerName=row.get("name"),
        priority=row.get("priority"),
        address=row.get("address"),
        phone=row.get("phone"),
        tenantId=row.get("tenant_id"),
    )


def list_customers(*, tenant_id: str | None, priority: str | None = None,
                    limit: int, offset: int) -> list[Customer]:
    clauses, params = db.build_filter([("tenant_id = %s", tenant_id), ("priority = %s", priority)])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(f"{_CUSTOMER_SELECT} {where} ORDER BY customer_id LIMIT %s OFFSET %s", params + (limit, offset))
    return [customer_from_row(r) for r in rows]


def get_customer(customer_id: str, *, tenant_id: str | None) -> Customer | None:
    clauses, params = db.build_filter([("customer_id = %s", customer_id), ("tenant_id = %s", tenant_id)])
    row = db.query_one(f"{_CUSTOMER_SELECT} WHERE {' AND '.join(clauses)}", params)
    return customer_from_row(row) if row else None


def service_point_from_row(row: dict) -> ServicePoint:
    return ServicePoint(
        mRID=identifiers.mrid_for("ServicePoint", row["service_point_id"]),
        name=row["service_point_id"],
        customerId=row.get("customer_id"),
        nodeId=row.get("node_id"),
        meterDeviceId=row.get("meter_device_id"),
        tenantId=row.get("tenant_id"),
    )


def list_service_points(*, tenant_id: str | None, customer_id: str | None = None,
                         node_id: str | None = None, limit: int, offset: int) -> list[ServicePoint]:
    clauses, params = db.build_filter([
        ("tenant_id = %s", tenant_id), ("customer_id = %s", customer_id), ("node_id = %s", node_id),
    ])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(f"{_SP_SELECT} {where} ORDER BY service_point_id LIMIT %s OFFSET %s", params + (limit, offset))
    return [service_point_from_row(r) for r in rows]


def get_service_point(service_point_id: str, *, tenant_id: str | None) -> ServicePoint | None:
    clauses, params = db.build_filter([("service_point_id = %s", service_point_id), ("tenant_id = %s", tenant_id)])
    row = db.query_one(f"{_SP_SELECT} WHERE {' AND '.join(clauses)}", params)
    return service_point_from_row(row) if row else None


def _group_service_points(tenant_id: str | None) -> list[dict]:
    clauses, params = db.build_filter([("tenant_id = %s", tenant_id)])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(f"{_SP_SELECT} {where} ORDER BY service_point_id", params)

    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        node_id, meter_id = r.get("node_id"), r.get("meter_device_id")
        key = ("sp", r["service_point_id"]) if node_id is None and meter_id is None else (node_id, meter_id)
        if key not in groups:
            groups[key] = {
                "node_id": node_id, "meter_device_id": meter_id,
                "tenant_id": r.get("tenant_id"), "customer_ids": [],
            }
            order.append(key)
        if r.get("customer_id"):
            groups[key]["customer_ids"].append(r["customer_id"])
    return [groups[k] for k in order]


def _usage_point_from_group(g: dict) -> UsagePoint:
    up_id = identifiers.usage_point_id(g["node_id"], g["meter_device_id"])
    return UsagePoint(
        mRID=identifiers.mrid_for("UsagePoint", up_id),
        name=up_id,
        nodeId=g["node_id"],
        meterDeviceId=g["meter_device_id"],
        customerIds=[identifiers.mrid_for("Customer", c) for c in g["customer_ids"]],
        tenantId=g["tenant_id"],
        synthesized=False,
    )


def _usage_point_fallback_devices(tenant_id: str | None) -> list[dict]:
    clauses, params = db.build_filter([("d.tenant_id = %s", tenant_id)])
    where = f"AND {' AND '.join(clauses)}" if clauses else ""
    return db.query_all(
        "SELECT d.device_id, d.site_name, d.tenant_id FROM devices d "
        "LEFT JOIN service_points sp ON sp.meter_device_id = d.device_id "
        f"WHERE sp.service_point_id IS NULL {where} ORDER BY d.device_id",
        params,
    )


def _usage_point_from_fallback_device(row: dict) -> UsagePoint:
    up_id = identifiers.usage_point_id(None, row["device_id"])
    return UsagePoint(
        mRID=identifiers.mrid_for("UsagePoint", up_id),
        name=up_id,
        meterDeviceId=row["device_id"],
        tenantId=row.get("tenant_id"),
        synthesized=True,
    )


def list_usage_points(*, tenant_id: str | None, limit: int, offset: int) -> list[UsagePoint]:
    points = [_usage_point_from_group(g) for g in _group_service_points(tenant_id)]
    points += [_usage_point_from_fallback_device(r) for r in _usage_point_fallback_devices(tenant_id)]
    return points[offset:offset + limit]


def get_usage_point(usage_point_id: str, *, tenant_id: str | None) -> UsagePoint | None:
    for p in list_usage_points(tenant_id=tenant_id, limit=10_000, offset=0):
        if p.name == usage_point_id:
            return p
    return None
