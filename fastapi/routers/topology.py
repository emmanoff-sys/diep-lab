"""ADMS M1 — Unified Network Model API.

CRUD + graph queries over the canonical grid topology (sql/013_network_model.sql).
This is the single source of truth all other ADMS modules read from:
  - OMS uses /topology/downstream/{node} to compute affected customers,
  - DMS uses the graph + switch state for state estimation and FLISR,
  - DERMS binds DER assets to grid nodes.

Reuses common.get_conn/query_* and auth.require_role, matching app.py style.
"""
import json

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import psycopg2

import common
from auth import require_role

router = APIRouter(prefix="/topology", tags=["topology"])

# Role bundles (mirrors app.py conventions): reads open to any authenticated
# principal, structural writes to engineer/admin, live switch ops to operator+.
READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")
WRITE_ROLES = ("admin", "engineer")
SWITCH_ROLES = ("operator", "engineer", "admin")


# --- schemas -----------------------------------------------------------------
class NodeIn(BaseModel):
    node_id: str = Field(..., examples=["FDR-02"])
    node_type: str = Field(..., examples=["feeder"])  # substation|feeder|transformer|switch|bus|meter|der|load
    name: str | None = None
    parent_id: str | None = None
    site_name: str | None = None
    device_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nominal_kv: float | None = None
    attrs: dict = Field(default_factory=dict)


class NodeUpdate(BaseModel):
    name: str | None = None
    parent_id: str | None = None
    site_name: str | None = None
    device_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nominal_kv: float | None = None
    attrs: dict | None = None


class EdgeIn(BaseModel):
    edge_id: str = Field(..., examples=["E-TIE-01"])
    from_node: str
    to_node: str
    edge_type: str = Field(default="line")  # line|switch|transformer|tie
    is_switchable: bool = False
    normally_closed: bool = True
    is_closed: bool = True
    rating_kw: float | None = None
    attrs: dict = Field(default_factory=dict)


class SwitchState(BaseModel):
    is_closed: bool


class CustomerIn(BaseModel):
    customer_id: str
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    priority: str = Field(default="standard")  # standard|medical|critical


class ServicePointIn(BaseModel):
    service_point_id: str
    customer_id: str | None = None
    node_id: str | None = None
    meter_device_id: str | None = None


# --- model version -----------------------------------------------------------
@router.get("/version")
def current_version(_p=Depends(require_role(*READ_ROLES))):
    row = common.query_one(
        "SELECT version, label, description, created_by, created_at "
        "FROM network_model_versions WHERE is_current = TRUE ORDER BY version DESC LIMIT 1"
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no current network model version")
    return row


# --- nodes -------------------------------------------------------------------
@router.get("/nodes")
def list_nodes(node_type: str | None = None, site_name: str | None = None,
               _p=Depends(require_role(*READ_ROLES))):
    clauses, params = [], []
    if node_type:
        clauses.append("node_type = %s")
        params.append(node_type)
    if site_name:
        clauses.append("site_name = %s")
        params.append(site_name)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = common.query_all(f"SELECT * FROM grid_nodes {where} ORDER BY node_id", tuple(params))
    return {"nodes": rows}


@router.get("/nodes/{node_id}")
def get_node(node_id: str, _p=Depends(require_role(*READ_ROLES))):
    row = common.query_one("SELECT * FROM grid_nodes WHERE node_id = %s", (node_id,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown node '{node_id}'")
    return row


@router.post("/nodes", status_code=201)
def create_node(node: NodeIn, _p=Depends(require_role(*WRITE_ROLES))):
    try:
        common.execute(
            "INSERT INTO grid_nodes (node_id, node_type, name, parent_id, site_name, device_id, "
            "latitude, longitude, nominal_kv, attrs, model_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            "(SELECT version FROM network_model_versions WHERE is_current=TRUE ORDER BY version DESC LIMIT 1))",
            (node.node_id, node.node_type, node.name, node.parent_id, node.site_name,
             node.device_id, node.latitude, node.longitude, node.nominal_kv, json.dumps(node.attrs)),
        )
    except psycopg2.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return common.query_one("SELECT * FROM grid_nodes WHERE node_id = %s", (node.node_id,))


@router.put("/nodes/{node_id}")
def update_node(node_id: str, body: NodeUpdate, _p=Depends(require_role(*WRITE_ROLES))):
    if common.query_one("SELECT 1 FROM grid_nodes WHERE node_id = %s", (node_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown node '{node_id}'")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return common.query_one("SELECT * FROM grid_nodes WHERE node_id = %s", (node_id,))
    sets, params = [], []
    for col, val in fields.items():
        sets.append(f"{col} = %s")
        params.append(json.dumps(val) if col == "attrs" else val)
    params.append(node_id)
    try:
        common.execute(f"UPDATE grid_nodes SET {', '.join(sets)} WHERE node_id = %s", tuple(params))
    except psycopg2.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return common.query_one("SELECT * FROM grid_nodes WHERE node_id = %s", (node_id,))


@router.delete("/nodes/{node_id}")
def delete_node(node_id: str, _p=Depends(require_role("admin"))):
    if common.query_one("SELECT 1 FROM grid_nodes WHERE node_id = %s", (node_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown node '{node_id}'")
    try:
        common.execute("DELETE FROM grid_nodes WHERE node_id = %s", (node_id,))
    except psycopg2.IntegrityError as exc:
        # Referenced by edges/service_points — surface as a conflict, don't 500.
        raise HTTPException(status_code=409, detail=f"node '{node_id}' is still referenced: {exc}")
    return {"status": "deleted", "node_id": node_id}


# --- edges -------------------------------------------------------------------
@router.get("/edges")
def list_edges(_p=Depends(require_role(*READ_ROLES))):
    return {"edges": common.query_all("SELECT * FROM grid_edges ORDER BY edge_id")}


@router.post("/edges", status_code=201)
def create_edge(edge: EdgeIn, _p=Depends(require_role(*WRITE_ROLES))):
    try:
        common.execute(
            "INSERT INTO grid_edges (edge_id, from_node, to_node, edge_type, is_switchable, "
            "normally_closed, is_closed, rating_kw, attrs, model_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            "(SELECT version FROM network_model_versions WHERE is_current=TRUE ORDER BY version DESC LIMIT 1))",
            (edge.edge_id, edge.from_node, edge.to_node, edge.edge_type, edge.is_switchable,
             edge.normally_closed, edge.is_closed, edge.rating_kw, json.dumps(edge.attrs)),
        )
    except psycopg2.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return common.query_one("SELECT * FROM grid_edges WHERE edge_id = %s", (edge.edge_id,))


@router.delete("/edges/{edge_id}")
def delete_edge(edge_id: str, _p=Depends(require_role("admin"))):
    if common.query_one("SELECT 1 FROM grid_edges WHERE edge_id = %s", (edge_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown edge '{edge_id}'")
    common.execute("DELETE FROM grid_edges WHERE edge_id = %s", (edge_id,))
    return {"status": "deleted", "edge_id": edge_id}


@router.patch("/edges/{edge_id}/switch")
def set_switch(edge_id: str, body: SwitchState, _p=Depends(require_role(*SWITCH_ROLES))):
    """Open/close a switchable edge. Used directly and by DMS/FLISR (M3)."""
    edge = common.query_one("SELECT * FROM grid_edges WHERE edge_id = %s", (edge_id,))
    if edge is None:
        raise HTTPException(status_code=404, detail=f"unknown edge '{edge_id}'")
    if not edge["is_switchable"]:
        raise HTTPException(status_code=409, detail=f"edge '{edge_id}' is not switchable")
    common.execute("UPDATE grid_edges SET is_closed = %s WHERE edge_id = %s", (body.is_closed, edge_id))
    return common.query_one("SELECT * FROM grid_edges WHERE edge_id = %s", (edge_id,))


# --- graph queries -----------------------------------------------------------
@router.get("/graph")
def graph(_p=Depends(require_role(*READ_ROLES))):
    """Full node+edge graph for rendering / client-side topology views."""
    return {
        "nodes": common.query_all("SELECT * FROM grid_nodes ORDER BY node_id"),
        "edges": common.query_all("SELECT * FROM grid_edges ORDER BY edge_id"),
    }


def _downstream_nodes(start: str, energized_only: bool = True) -> list[str]:
    """BFS from `start` following directed edges. When energized_only, traverse
    only CLOSED edges — so an open switch (FLISR) correctly severs the subtree."""
    edges = common.query_all("SELECT from_node, to_node, is_closed FROM grid_edges")
    adj: dict[str, list[str]] = {}
    for e in edges:
        if energized_only and not e["is_closed"]:
            continue
        adj.setdefault(e["from_node"], []).append(e["to_node"])
    seen, order, stack = {start}, [start], [start]
    while stack:
        cur = stack.pop()
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                order.append(nxt)
                stack.append(nxt)
    return order


@router.get("/downstream/{node_id}")
def downstream(node_id: str, energized_only: bool = True, _p=Depends(require_role(*READ_ROLES))):
    """Nodes reachable downstream of node_id, plus the meters/customers served.
    OMS reuses this to resolve the affected-customer set for an outage."""
    if common.query_one("SELECT 1 FROM grid_nodes WHERE node_id = %s", (node_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown node '{node_id}'")
    reachable = _downstream_nodes(node_id, energized_only)
    nodes = common.query_all(
        "SELECT node_id, node_type, name, device_id FROM grid_nodes WHERE node_id = ANY(%s)",
        (reachable,),
    )
    meter_nodes = [n["node_id"] for n in nodes if n["node_type"] == "meter"]
    sps = common.query_all(
        "SELECT sp.service_point_id, sp.customer_id, sp.node_id, sp.meter_device_id, "
        "c.name, c.priority FROM service_points sp "
        "LEFT JOIN customers c ON c.customer_id = sp.customer_id "
        "WHERE sp.node_id = ANY(%s)",
        (reachable,),
    )
    by_priority: dict[str, int] = {}
    for sp in sps:
        by_priority[sp["priority"] or "standard"] = by_priority.get(sp["priority"] or "standard", 0) + 1
    return {
        "root": node_id,
        "energized_only": energized_only,
        "reachable_nodes": reachable,
        "meter_nodes": meter_nodes,
        "affected_service_points": sps,
        "affected_customer_count": len(sps),
        "affected_by_priority": by_priority,
    }


# --- customers + service points ----------------------------------------------
@router.get("/customers")
def list_customers(_p=Depends(require_role(*READ_ROLES))):
    return {"customers": common.query_all("SELECT * FROM customers ORDER BY customer_id")}


@router.post("/customers", status_code=201)
def create_customer(c: CustomerIn, _p=Depends(require_role(*WRITE_ROLES))):
    try:
        common.execute(
            "INSERT INTO customers (customer_id, name, address, phone, priority) VALUES (%s,%s,%s,%s,%s)",
            (c.customer_id, c.name, c.address, c.phone, c.priority),
        )
    except psycopg2.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return common.query_one("SELECT * FROM customers WHERE customer_id = %s", (c.customer_id,))


@router.get("/service-points")
def list_service_points(_p=Depends(require_role(*READ_ROLES))):
    return {"service_points": common.query_all("SELECT * FROM service_points ORDER BY service_point_id")}


@router.post("/service-points", status_code=201)
def create_service_point(sp: ServicePointIn, _p=Depends(require_role(*WRITE_ROLES))):
    try:
        common.execute(
            "INSERT INTO service_points (service_point_id, customer_id, node_id, meter_device_id) "
            "VALUES (%s,%s,%s,%s)",
            (sp.service_point_id, sp.customer_id, sp.node_id, sp.meter_device_id),
        )
    except psycopg2.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return common.query_one("SELECT * FROM service_points WHERE service_point_id = %s", (sp.service_point_id,))
