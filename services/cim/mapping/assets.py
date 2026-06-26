"""Maps `der_assets` rows to Asset. Smartmeters and other non-DER device
types have no row here -- a documented gap (see SUPPORTED_OBJECTS.md), not
a silently-sparse result.
"""
from __future__ import annotations

from .. import db, identifiers
from ..models import Asset

_ASSET_SELECT = (
    "SELECT der_id, der_type, node_id, rated_kw, rated_kwh, controllable, vpp_group, tenant_id "
    "FROM der_assets"
)


def asset_from_row(row: dict) -> Asset:
    return Asset(
        mRID=identifiers.mrid_for("Asset", row["der_id"]),
        name=row["der_id"],
        assetType=row.get("der_type"),
        ratedKw=row.get("rated_kw"),
        ratedKwh=row.get("rated_kwh"),
        controllable=row.get("controllable"),
        vppGroup=row.get("vpp_group"),
        nodeId=row.get("node_id"),
        tenantId=row.get("tenant_id"),
    )


def list_assets(*, tenant_id: str | None, der_type: str | None = None,
                vpp_group: str | None = None, limit: int, offset: int) -> list[Asset]:
    clauses, params = db.build_filter([
        ("tenant_id = %s", tenant_id), ("der_type = %s", der_type), ("vpp_group = %s", vpp_group),
    ])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(f"{_ASSET_SELECT} {where} ORDER BY der_id LIMIT %s OFFSET %s", params + (limit, offset))
    return [asset_from_row(r) for r in rows]


def get_asset(der_id: str, *, tenant_id: str | None) -> Asset | None:
    clauses, params = db.build_filter([("der_id = %s", der_id), ("tenant_id = %s", tenant_id)])
    row = db.query_one(f"{_ASSET_SELECT} WHERE {' AND '.join(clauses)}", params)
    return asset_from_row(row) if row else None
