"""Maps `grid_nodes`/`grid_edges` rows to ConnectivityNode, Terminal,
Transformer, Feeder. See CIM_MAPPING_GUIDE.md for the Terminal-synthesis
rationale (no dedicated table backs it).
"""
from __future__ import annotations

from .. import db, identifiers
from ..models import ConnectivityNode, Feeder, Terminal, Transformer

_NODE_SELECT = (
    "SELECT node_id, node_type, name, parent_id, site_name, device_id, "
    "latitude, longitude, nominal_kv, tenant_id FROM grid_nodes"
)
_EDGE_SELECT = "SELECT edge_id, from_node, to_node, edge_type, tenant_id FROM grid_edges"


def connectivity_node_from_row(row: dict) -> ConnectivityNode:
    return ConnectivityNode(
        mRID=identifiers.mrid_for("ConnectivityNode", row["node_id"]),
        name=row.get("name") or row["node_id"],
        nodeType=row.get("node_type"),
        parentMRID=identifiers.mrid_for("ConnectivityNode", row["parent_id"]) if row.get("parent_id") else None,
        siteName=row.get("site_name"),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        nominalKv=row.get("nominal_kv"),
        tenantId=row.get("tenant_id"),
    )


def _equipment_from_row(cls, row: dict) -> "Transformer | Feeder":
    return cls(
        mRID=identifiers.mrid_for(cls.__name__, row["node_id"]),
        name=row.get("name") or row["node_id"],
        nominalKv=row.get("nominal_kv"),
        siteName=row.get("site_name"),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        tenantId=row.get("tenant_id"),
        **({"parentMRID": identifiers.mrid_for("ConnectivityNode", row["parent_id"])}
           if cls is Transformer and row.get("parent_id") else {}),
    )


def list_connectivity_nodes(*, tenant_id: str | None, node_type: str | None = None,
                             site_name: str | None = None, limit: int, offset: int) -> list[ConnectivityNode]:
    clauses, params = db.build_filter([
        ("tenant_id = %s", tenant_id),
        ("node_type = %s", node_type),
        ("site_name = %s", site_name),
    ])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(f"{_NODE_SELECT} {where} ORDER BY node_id LIMIT %s OFFSET %s", params + (limit, offset))
    return [connectivity_node_from_row(r) for r in rows]


def get_connectivity_node(node_id: str, *, tenant_id: str | None) -> ConnectivityNode | None:
    clauses, params = db.build_filter([("node_id = %s", node_id), ("tenant_id = %s", tenant_id)])
    row = db.query_one(f"{_NODE_SELECT} WHERE {' AND '.join(clauses)}", params)
    return connectivity_node_from_row(row) if row else None


def _list_equipment(cls, *, tenant_id: str | None, site_name: str | None, limit: int, offset: int):
    node_type = "transformer" if cls is Transformer else "feeder"
    clauses, params = db.build_filter([("tenant_id = %s", tenant_id), ("site_name = %s", site_name)])
    extra = f" AND {' AND '.join(clauses)}" if clauses else ""
    rows = db.query_all(
        f"{_NODE_SELECT} WHERE node_type = '{node_type}'{extra} ORDER BY node_id LIMIT %s OFFSET %s",
        params + (limit, offset),
    )
    return [_equipment_from_row(cls, r) for r in rows]


def _get_equipment(cls, node_id: str, *, tenant_id: str | None):
    node_type = "transformer" if cls is Transformer else "feeder"
    clauses, params = db.build_filter([("node_id = %s", node_id), ("tenant_id = %s", tenant_id)])
    extra = f" AND {' AND '.join(clauses)}" if clauses else ""
    row = db.query_one(f"{_NODE_SELECT} WHERE node_type = '{node_type}'{extra}", params)
    return _equipment_from_row(cls, row) if row else None


def list_transformers(*, tenant_id, site_name=None, limit, offset):
    return _list_equipment(Transformer, tenant_id=tenant_id, site_name=site_name, limit=limit, offset=offset)


def get_transformer(node_id: str, *, tenant_id):
    return _get_equipment(Transformer, node_id, tenant_id=tenant_id)


def list_feeders(*, tenant_id, site_name=None, limit, offset):
    return _list_equipment(Feeder, tenant_id=tenant_id, site_name=site_name, limit=limit, offset=offset)


def get_feeder(node_id: str, *, tenant_id):
    return _get_equipment(Feeder, node_id, tenant_id=tenant_id)


def list_terminals(*, tenant_id: str | None, edge_id: str | None = None,
                    node_id: str | None = None, limit: int, offset: int) -> list[Terminal]:
    """Synthesizes 2 Terminals per grid_edges row + 1 per grid_nodes row
    with no edge referencing it (a leaf DER/meter still needs a Terminal in
    real CIM topology, even with degree 1)."""
    terminals: list[Terminal] = []

    edge_clauses, edge_params = db.build_filter([("tenant_id = %s", tenant_id), ("edge_id = %s", edge_id)])
    edge_where = f"WHERE {' AND '.join(edge_clauses)}" if edge_clauses else ""
    for e in db.query_all(f"{_EDGE_SELECT} {edge_where} ORDER BY edge_id", edge_params):
        terminals.append(Terminal(
            mRID=identifiers.mrid_for("Terminal", identifiers.terminal_id(e["edge_id"], 1)),
            name=identifiers.terminal_id(e["edge_id"], 1),
            sequenceNumber=1,
            connectivityNodeMRID=identifiers.mrid_for("ConnectivityNode", e["from_node"]),
            conductingEquipmentRef=e["edge_id"],
            tenantId=e.get("tenant_id"),
        ))
        terminals.append(Terminal(
            mRID=identifiers.mrid_for("Terminal", identifiers.terminal_id(e["edge_id"], 2)),
            name=identifiers.terminal_id(e["edge_id"], 2),
            sequenceNumber=2,
            connectivityNodeMRID=identifiers.mrid_for("ConnectivityNode", e["to_node"]),
            conductingEquipmentRef=e["edge_id"],
            tenantId=e.get("tenant_id"),
        ))

    if not edge_id:  # leaf-node terminals only make sense for an unfiltered/edge-less query
        leaf_clauses, leaf_params = db.build_filter([("n.tenant_id = %s", tenant_id), ("n.node_id = %s", node_id)])
        leaf_where = f"AND {' AND '.join(leaf_clauses)}" if leaf_clauses else ""
        leaves = db.query_all(
            "SELECT n.node_id, n.tenant_id FROM grid_nodes n "
            "WHERE NOT EXISTS (SELECT 1 FROM grid_edges e WHERE e.from_node = n.node_id OR e.to_node = n.node_id) "
            f"{leaf_where} ORDER BY n.node_id",
            leaf_params,
        )
        for n in leaves:
            terminals.append(Terminal(
                mRID=identifiers.mrid_for("Terminal", identifiers.leaf_terminal_id(n["node_id"])),
                name=identifiers.leaf_terminal_id(n["node_id"]),
                sequenceNumber=1,
                connectivityNodeMRID=identifiers.mrid_for("ConnectivityNode", n["node_id"]),
                conductingEquipmentRef=n["node_id"],
                tenantId=n.get("tenant_id"),
            ))

    if node_id and not edge_id:
        terminals = [t for t in terminals if t.conductingEquipmentRef == node_id
                     or t.connectivityNodeMRID == identifiers.mrid_for("ConnectivityNode", node_id)]

    return terminals[offset:offset + limit]
