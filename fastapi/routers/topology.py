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
import psycopg2.extras

import common
import topology_history
import topology_publish
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
    node_type: str = Field(..., examples=["feeder"])  # substation|feeder|transformer|switch|recloser|bus|meter|der|load
    name: str | None = None
    parent_id: str | None = None
    site_name: str | None = None
    device_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nominal_kv: float | None = None
    # P5-M1 electrical attributes (consumed by state estimation / power flow):
    phases: str = Field(default="ABC", examples=["ABC", "A"])
    base_load_kw: float = 0.0
    base_load_kvar: float = 0.0
    load_class: str | None = None
    attrs: dict = Field(default_factory=dict)


class NodeUpdate(BaseModel):
    name: str | None = None
    parent_id: str | None = None
    site_name: str | None = None
    device_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nominal_kv: float | None = None
    phases: str | None = None
    base_load_kw: float | None = None
    base_load_kvar: float | None = None
    load_class: str | None = None
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
    # P5-M1 electrical attributes (series impedance referred to the downstream base):
    resistance_r_ohm: float | None = None
    reactance_x_ohm: float | None = None
    length_km: float | None = None
    ampacity_a: float | None = None
    phases: str = Field(default="ABC", examples=["ABC", "A"])
    attrs: dict = Field(default_factory=dict)


class SwitchState(BaseModel):
    is_closed: bool


class VersionIn(BaseModel):
    label: str = Field(..., examples=["geojson-import-2026-06-25"])
    description: str | None = None
    # WP-006-04: optional model content published atomically with the version.
    # Same canonical dict shapes topology/loader.py's importer takes; an empty
    # payload keeps the original metadata-only publish behaviour.
    site_name: str | None = None
    nodes: list[NodeIn] = Field(default_factory=list)
    edges: list[EdgeIn] = Field(default_factory=list)


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


# --- version history & diff (WP-006-05) ---------------------------------------
_VERSION_COLS = "version, label, description, created_by, is_current, created_at"


@router.get("/versions")
def list_versions(limit: int = 50, offset: int = 0,
                  _p=Depends(require_role(*READ_ROLES))):
    """Version history, newest first (WP-006-05)."""
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    total = common.query_one("SELECT COUNT(*) AS n FROM network_model_versions")["n"]
    rows = common.query_all(
        f"SELECT {_VERSION_COLS} FROM network_model_versions "
        "ORDER BY version DESC LIMIT %s OFFSET %s", (limit, offset))
    return {"total": total, "limit": limit, "offset": offset, "versions": rows}


# NOTE: declared before /versions/{version} so "diff" is not captured as a
# version path parameter.
@router.get("/versions/diff")
def diff_versions(from_version: int, to_version: int,
                  _p=Depends(require_role(*READ_ROLES))):
    """Write-stamp diff between two published versions (WP-006-05).

    Semantics per AR-054 F-AR054-02: grid rows carry the version that LAST
    wrote them (writes are stamped, states are not snapshotted). The diff
    therefore reports the rows touched by versions in (from, to] with their
    CURRENT content; pre-overwrite values and deleted rows are not
    reconstructable. The response says so via `"semantics": "write-stamp"`.
    """
    errors = topology_history.validate_diff_range(from_version, to_version)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    for v in (from_version, to_version):
        if common.query_one(
                "SELECT 1 FROM network_model_versions WHERE version = %s", (v,)) is None:
            raise HTTPException(status_code=404, detail=f"unknown network model version {v}")

    versions_in_range = common.query_all(
        f"SELECT {_VERSION_COLS} FROM network_model_versions "
        "WHERE version > %s AND version <= %s ORDER BY version",
        (from_version, to_version))
    nodes = common.query_all(
        "SELECT node_id, node_type, name, site_name, model_version FROM grid_nodes "
        "WHERE model_version > %s AND model_version <= %s "
        "ORDER BY model_version, node_id", (from_version, to_version))
    edges = common.query_all(
        "SELECT edge_id, from_node, to_node, edge_type, is_closed, model_version "
        "FROM grid_edges WHERE model_version > %s AND model_version <= %s "
        "ORDER BY model_version, edge_id", (from_version, to_version))

    summary = topology_history.summarize_diff(versions_in_range, nodes, edges)
    return {"from_version": from_version, "to_version": to_version, **summary}


@router.get("/versions/{version}")
def get_version(version: int, _p=Depends(require_role(*READ_ROLES))):
    """Single version metadata plus counts of rows it last wrote (WP-006-05)."""
    row = common.query_one(
        f"SELECT {_VERSION_COLS} FROM network_model_versions WHERE version = %s", (version,))
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown network model version {version}")
    nodes_stamped = common.query_one(
        "SELECT COUNT(*) AS n FROM grid_nodes WHERE model_version = %s", (version,))["n"]
    edges_stamped = common.query_one(
        "SELECT COUNT(*) AS n FROM grid_edges WHERE model_version = %s", (version,))["n"]
    return {**row, "nodes_stamped": nodes_stamped, "edges_stamped": edges_stamped,
            "semantics": topology_history.DIFF_SEMANTICS}


# Column lists for the WP-006-04 content publish. Mirror topology/loader.py's
# _NODE_COLS/_EDGE_COLS convention (that module and this router deliberately
# run the same SQL inline rather than importing each other — see the loader's
# module docstring), extended with the columns NodeIn/EdgeIn already carry
# that the CLI loader does not (device_id, load_class, rating_kw).
_PUB_NODE_COLS = ["node_id", "node_type", "name", "site_name", "device_id",
                  "latitude", "longitude", "nominal_kv", "phases", "base_load_kw",
                  "base_load_kvar", "load_class", "attrs", "model_version"]
_PUB_EDGE_COLS = ["edge_id", "from_node", "to_node", "edge_type", "is_switchable",
                  "normally_closed", "is_closed", "rating_kw", "resistance_r_ohm",
                  "reactance_x_ohm", "length_km", "ampacity_a", "phases", "attrs",
                  "model_version"]


@router.post("/versions", status_code=201)
def publish_version(body: VersionIn, p=Depends(require_role(*WRITE_ROLES))):
    """Publish a new network model version and mark it current (WP-006-04).

    With an empty payload this keeps the original metadata-only behaviour
    (P2 Gap 1). With `nodes`/`edges` supplied it also upserts the model
    content stamped with the new version — the "portal publish button"
    surface the loader's docstring reserves for this endpoint.

    All of it happens in ONE transaction: the previous two-statement
    autocommit publish could fail between demote and insert and leave the
    system with no current version (breaking every node/edge INSERT's
    current-version subselect), and neither it nor the CLI loader could
    publish version+content all-or-nothing. Concurrent publishes are
    serialised with a transaction-scoped advisory lock, closing the race
    where two publishers both demote then both insert and leave two
    is_current rows."""
    errors = topology_publish.validate_publish_payload(
        [n.model_dump() for n in body.nodes], [e.model_dump() for e in body.edges])
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    conn = common.get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('topology.publish_version'))")
        cur.execute("UPDATE network_model_versions SET is_current = FALSE WHERE is_current = TRUE")
        cur.execute(
            "INSERT INTO network_model_versions (label, description, created_by, is_current) "
            "VALUES (%s, %s, %s, TRUE) "
            "RETURNING version, label, description, created_by, is_current, created_at",
            (body.label, body.description, p.name),
        )
        version_row = dict(cur.fetchone())
        version = version_row["version"]

        if body.site_name:
            cur.execute(
                "INSERT INTO sites (site_name, site_type) VALUES (%s, 'feeder') "
                "ON CONFLICT (site_name) DO NOTHING", (body.site_name,))

        for n in body.nodes:
            row = (n.node_id, n.node_type, n.name, n.site_name or body.site_name,
                   n.device_id, n.latitude, n.longitude, n.nominal_kv, n.phases,
                   n.base_load_kw, n.base_load_kvar, n.load_class,
                   json.dumps(n.attrs), version)
            cur.execute(
                f"INSERT INTO grid_nodes ({', '.join(_PUB_NODE_COLS)}) "
                f"VALUES ({', '.join(['%s'] * len(_PUB_NODE_COLS))}) "
                "ON CONFLICT (node_id) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in _PUB_NODE_COLS if c != "node_id"),
                row,
            )
        # parent_id in a second pass: grid_nodes.parent_id is a self-FK and the
        # payload is not guaranteed parent-before-child (same as the loader).
        for n in body.nodes:
            if n.parent_id:
                cur.execute("UPDATE grid_nodes SET parent_id = %s WHERE node_id = %s",
                            (n.parent_id, n.node_id))

        for e in body.edges:
            row = (e.edge_id, e.from_node, e.to_node, e.edge_type, e.is_switchable,
                   e.normally_closed, e.is_closed, e.rating_kw, e.resistance_r_ohm,
                   e.reactance_x_ohm, e.length_km, e.ampacity_a, e.phases,
                   json.dumps(e.attrs), version)
            cur.execute(
                f"INSERT INTO grid_edges ({', '.join(_PUB_EDGE_COLS)}) "
                f"VALUES ({', '.join(['%s'] * len(_PUB_EDGE_COLS))}) "
                "ON CONFLICT (edge_id) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in _PUB_EDGE_COLS if c != "edge_id"),
                row,
            )

        conn.commit()
        return {**version_row,
                "nodes_written": len(body.nodes), "edges_written": len(body.edges)}
    except psycopg2.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
            "latitude, longitude, nominal_kv, phases, base_load_kw, base_load_kvar, load_class, "
            "attrs, model_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            "(SELECT version FROM network_model_versions WHERE is_current=TRUE ORDER BY version DESC LIMIT 1))",
            (node.node_id, node.node_type, node.name, node.parent_id, node.site_name,
             node.device_id, node.latitude, node.longitude, node.nominal_kv, node.phases,
             node.base_load_kw, node.base_load_kvar, node.load_class, json.dumps(node.attrs)),
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
            "normally_closed, is_closed, rating_kw, resistance_r_ohm, reactance_x_ohm, length_km, "
            "ampacity_a, phases, attrs, model_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
            "(SELECT version FROM network_model_versions WHERE is_current=TRUE ORDER BY version DESC LIMIT 1))",
            (edge.edge_id, edge.from_node, edge.to_node, edge.edge_type, edge.is_switchable,
             edge.normally_closed, edge.is_closed, edge.rating_kw, edge.resistance_r_ohm,
             edge.reactance_x_ohm, edge.length_km, edge.ampacity_a, edge.phases, json.dumps(edge.attrs)),
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


@router.get("/downstream/{node_id}")
def downstream(node_id: str, energized_only: bool = True, _p=Depends(require_role(*READ_ROLES))):
    """Nodes reachable downstream of node_id, plus the meters/customers served.
    OMS reuses this to resolve the affected-customer set for an outage."""
    if common.query_one("SELECT 1 FROM grid_nodes WHERE node_id = %s", (node_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown node '{node_id}'")
    reachable = common.downstream_node_ids(node_id, energized_only)
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


# --- topology validation + graph analysis (P5-M1) ----------------------------
def _graph_rows() -> tuple[list[dict], list[dict]]:
    nodes = common.query_all(
        "SELECT node_id, node_type, name, parent_id, nominal_kv, phases FROM grid_nodes")
    edges = common.query_all(
        "SELECT edge_id, from_node, to_node, edge_type, is_switchable, normally_closed, "
        "is_closed FROM grid_edges")
    return nodes, edges


def _components(node_ids: set, undirected_adj: dict) -> list[list[str]]:
    """Connected components of an undirected adjacency map."""
    seen, comps = set(), []
    for start in sorted(node_ids):
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            c = stack.pop()
            comp.append(c)
            for n in undirected_adj.get(c, ()):
                if n not in seen:
                    seen.add(n)
                    stack.append(n)
        comps.append(sorted(comp))
    return comps


def validate_topology() -> dict:
    """Structural + electrical sanity of the network model (read-only). Reports
    orphans, source count, parent/edge hierarchy consistency, and — the core P5-M1
    capability — loop detection on both the *structural* graph (all edges) and the
    *operational* graph (currently-closed edges). A radial distribution network is
    a forest when operated; ties create intentional structural loops that must stay
    open. Errors = conditions that break radial-network assumptions; warnings =
    things to review (missing impedance, unenergized sections)."""
    nodes, edges = _graph_rows()
    node_ids = {n["node_id"] for n in nodes}
    by_id = {n["node_id"]: n for n in nodes}
    sources = [n["node_id"] for n in nodes if n["node_type"] == "substation"]

    # adjacency maps
    und: dict[str, set] = {nid: set() for nid in node_ids}
    closed_und: dict[str, set] = {nid: set() for nid in node_ids}
    closed_parents: dict[str, list[str]] = {nid: [] for nid in node_ids}
    edge_between: set = set()
    for e in edges:
        a, b = e["from_node"], e["to_node"]
        und[a].add(b); und[b].add(a)
        edge_between.add((a, b)); edge_between.add((b, a))
        if e["is_closed"]:
            closed_und[a].add(b); closed_und[b].add(a)
            closed_parents[b].append(a)

    errors, warnings = [], []

    # 1) sources
    if not sources:
        errors.append("no substation (energization source) in the model")
    elif len(sources) > 1:
        warnings.append(f"{len(sources)} substations present: {sources}")

    # 2) orphans — nodes in no structural component containing a source
    comps = _components(node_ids, und)
    src_set = set(sources)
    energizable = set()
    for comp in comps:
        if src_set.intersection(comp):
            energizable.update(comp)
    orphans = sorted(node_ids - energizable - src_set)
    if orphans:
        errors.append(f"{len(orphans)} node(s) not connected to any source: {orphans}")

    # 3) cyclomatic loop count: independent_loops = |E| - |N| + components
    def loops(adj: dict) -> int:
        ec = sum(len(v) for v in adj.values()) // 2
        cc = len(_components(node_ids, adj))
        return ec - len(node_ids) + cc

    structural_loops = loops(und)
    operational_loops = loops(closed_und)
    if operational_loops > 0:
        errors.append(f"{operational_loops} loop(s) in the energized (closed-switch) "
                      "network — radial operation requires a forest; a tie/parallel "
                      "path is closed")
    # nodes presently fed from two closed paths (parallel feed)
    multi_fed = sorted(nid for nid, ps in closed_parents.items() if len(ps) > 1)
    if multi_fed:
        errors.append(f"node(s) with multiple closed feeds: {multi_fed}")

    # informational: open switches whose closure would form a loop (back-feed ties)
    loop_closing = []
    closed_reach = {nid: comp for comp in _components(node_ids, closed_und) for nid in comp}
    for e in edges:
        if not e["is_closed"] and e["is_switchable"]:
            if closed_reach.get(e["from_node"]) is not None and \
               closed_reach.get(e["from_node"]) == closed_reach.get(e["to_node"]):
                loop_closing.append(e["edge_id"])

    # 4) parent/edge hierarchy consistency
    hierarchy_issues = []
    for n in nodes:
        p = n["parent_id"]
        if p is None:
            if n["node_type"] != "substation":
                warnings.append(f"non-substation node '{n['node_id']}' has no parent_id")
            continue
        if p not in node_ids:
            errors.append(f"node '{n['node_id']}' parent_id '{p}' does not exist")
        elif (p, n["node_id"]) not in edge_between:
            hierarchy_issues.append(n["node_id"])
    if hierarchy_issues:
        warnings.append(f"node(s) whose parent_id has no connecting edge: {sorted(hierarchy_issues)}")

    # 5) electrical completeness (warnings — needed by P5-M2/M3)
    missing_z = [e["edge_id"] for e in common.query_all(
        "SELECT edge_id FROM grid_edges WHERE edge_type IN ('line','transformer','tie') "
        "AND (resistance_r_ohm IS NULL OR reactance_x_ohm IS NULL)")]
    if missing_z:
        warnings.append(f"{len(missing_z)} edge(s) missing series impedance: {missing_z}")

    radial = operational_loops == 0 and not multi_fed
    return {
        "ok": not errors,
        "radial": radial,
        "counts": {"nodes": len(node_ids), "edges": len(edges), "sources": len(sources),
                   "components": len(comps)},
        "structural_loops": structural_loops,
        "operational_loops": operational_loops,
        "loop_closing_switches": sorted(loop_closing),
        "orphan_nodes": orphans,
        "multi_fed_nodes": multi_fed,
        "errors": errors,
        "warnings": warnings,
    }


@router.get("/validate")
def validate(_p=Depends(require_role(*READ_ROLES))):
    return validate_topology()


@router.get("/adjacency")
def adjacency(closed_only: bool = False, _p=Depends(require_role(*READ_ROLES))):
    """Adjacency + connected components for client graph rendering / analysis.
    closed_only=true uses only currently-closed edges (operational topology)."""
    nodes, edges = _graph_rows()
    node_ids = {n["node_id"] for n in nodes}
    und: dict[str, set] = {nid: set() for nid in node_ids}
    out_adj: dict[str, list[dict]] = {nid: [] for nid in node_ids}
    for e in edges:
        if closed_only and not e["is_closed"]:
            continue
        und[e["from_node"]].add(e["to_node"]); und[e["to_node"]].add(e["from_node"])
        out_adj[e["from_node"]].append({"to": e["to_node"], "edge_id": e["edge_id"],
                                        "edge_type": e["edge_type"], "is_closed": e["is_closed"]})
    comps = _components(node_ids, und)
    return {
        "closed_only": closed_only,
        "adjacency": out_adj,
        "components": comps,
        "component_count": len(comps),
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
