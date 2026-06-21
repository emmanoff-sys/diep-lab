"""ADMS M3 — Distribution Management System (DMS) basics.

Three lightweight, topology-driven capabilities (all stubs, clearly labelled):

  - GET  /dms/state_estimation        — estimate voltage/load at unmonitored
                                          nodes by propagating live telemetry
                                          over the M1 graph.
  - POST /dms/flisr/simulate          — Fault Location, Isolation & Service
                                          Restoration: isolate a fault by
                                          opening the nearest upstream switch,
                                          restore lost load via a normally-open
                                          tie. Plans on an in-memory copy of the
                                          graph; only mutates switch state when
                                          execute=true.
  - GET  /dms/voltvar/recommendations — rule-based Volt/VAR suggestions from
                                          measured/estimated voltages.

These consume the M1 network model + live telemetry; no real power-flow solver.
"""
import os
import uuid
import json

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

import common
from auth import require_role

router = APIRouter(prefix="/dms", tags=["dms"])

READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")
EXEC_ROLES = ("operator", "engineer", "admin")

# State-estimation voltage-drop coefficient (pu per kW of downstream load) and
# Volt/VAR bands — stub tunables.
DROP_PU_PER_KW = float(os.getenv("DMS_DROP_PU_PER_KW", "0.00008"))
VV_PU_LOW = float(os.getenv("DMS_VV_PU_LOW", "0.95"))
VV_PU_HIGH = float(os.getenv("DMS_VV_PU_HIGH", "1.05"))
VV_LV_LOW = float(os.getenv("DMS_VV_LV_LOW", "216"))   # 230V -10%
VV_LV_HIGH = float(os.getenv("DMS_VV_LV_HIGH", "253"))  # 230V +10%
TELEMETRY_FRESH_S = int(os.getenv("DMS_TELEMETRY_FRESH_S", "600"))


# --- graph + measurement helpers ---------------------------------------------
def _load_nodes() -> list[dict]:
    return common.query_all(
        "SELECT node_id, node_type, name, parent_id, device_id, nominal_kv FROM grid_nodes")


def _load_edges() -> list[dict]:
    return common.query_all(
        "SELECT edge_id, from_node, to_node, edge_type, is_switchable, normally_closed, is_closed "
        "FROM grid_edges")


def _reach(edges: list[dict], sources: list[str]) -> set:
    """Nodes reachable from sources following CLOSED directed edges."""
    adj: dict[str, list[str]] = {}
    for e in edges:
        if e["is_closed"]:
            adj.setdefault(e["from_node"], []).append(e["to_node"])
    seen, stack = set(sources), list(sources)
    while stack:
        c = stack.pop()
        for n in adj.get(c, []):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def _substations(nodes: list[dict]) -> list[str]:
    return [n["node_id"] for n in nodes if n["node_type"] == "substation"]


def _measurements() -> dict:
    """Latest fresh telemetry per device-linked node: {device_id: {...}}."""
    rows = common.query_all(
        "SELECT DISTINCT ON (device_id) device_id, voltage, power_kw, grid_import_kw, "
        "EXTRACT(EPOCH FROM (now() - time)) AS age "
        "FROM telemetry ORDER BY device_id, time DESC")
    out = {}
    for r in rows:
        if r["age"] is not None and float(r["age"]) <= TELEMETRY_FRESH_S:
            out[r["device_id"]] = r
    return out


def _service_points_in(node_ids) -> list[dict]:
    if not node_ids:
        return []
    return common.query_all(
        "SELECT sp.service_point_id, sp.customer_id, sp.node_id, c.priority "
        "FROM service_points sp LEFT JOIN customers c ON c.customer_id = sp.customer_id "
        "WHERE sp.node_id = ANY(%s)", (list(node_ids),))


# --- state estimation --------------------------------------------------------
def _estimate_state() -> list[dict]:
    nodes = _load_nodes()
    edges = _load_edges()
    meas = _measurements()
    by_id = {n["node_id"]: n for n in nodes}
    children: dict[str, list[str]] = {}
    for e in edges:
        if e["is_closed"]:
            children.setdefault(e["from_node"], []).append(e["to_node"])

    # measured load per node (kW) from telemetry on its linked device.
    load = {}
    for n in nodes:
        m = meas.get(n["device_id"]) if n["device_id"] else None
        if m is not None:
            load[n["node_id"]] = max(float(m.get("grid_import_kw") or m.get("power_kw") or 0.0), 0.0)
        else:
            load[n["node_id"]] = 0.0

    # downstream aggregate load (subtree), memoized DFS.
    agg: dict[str, float] = {}

    def subtree_load(nid: str, seen: set) -> float:
        if nid in agg:
            return agg[nid]
        if nid in seen:
            return 0.0
        seen.add(nid)
        total = load.get(nid, 0.0) + sum(subtree_load(c, seen) for c in children.get(nid, []))
        agg[nid] = total
        return total

    for n in nodes:
        subtree_load(n["node_id"], set())

    # voltage pu: 1.0 at substations, drop proportional to downstream load.
    energized = _reach(edges, _substations(nodes))
    # voltage by walking from each node up to a substation, summing drops.
    parent = {n["node_id"]: n["parent_id"] for n in nodes}

    def v_pu(nid: str) -> float:
        chain, cur, guard = [], nid, 0
        while cur is not None and guard < 100:
            chain.append(cur)
            if by_id.get(cur, {}).get("node_type") == "substation":
                break
            cur = parent.get(cur)
            guard += 1
        v = 1.0
        for node_id in reversed(chain):
            v -= DROP_PU_PER_KW * agg.get(node_id, 0.0)
        return round(v, 4)

    result = []
    for n in nodes:
        nid = n["node_id"]
        m = meas.get(n["device_id"]) if n["device_id"] else None
        result.append({
            "node_id": nid,
            "node_type": n["node_type"],
            "name": n["name"],
            "energized": nid in energized,
            "monitored": m is not None,
            "measured_voltage": (round(float(m["voltage"]), 2) if m and m.get("voltage") is not None else None),
            "measured_power_kw": (round(float(m["power_kw"]), 2) if m and m.get("power_kw") is not None else None),
            "downstream_load_kw": round(agg.get(nid, 0.0), 2),
            "estimated_voltage_pu": v_pu(nid),
        })
    return result


@router.get("/state_estimation")
def state_estimation(_p=Depends(require_role(*READ_ROLES))):
    est = _estimate_state()
    return {
        "method": "stub: downstream-load voltage-drop propagation over M1 graph",
        "monitored_nodes": sum(1 for e in est if e["monitored"]),
        "total_nodes": len(est),
        "nodes": est,
    }


# --- FLISR -------------------------------------------------------------------
class FlisrRequest(BaseModel):
    fault_node: str | None = Field(None, examples=["TX-01"])
    fault_edge: str | None = Field(None, examples=["E-TX-BUS"])
    execute: bool = False


@router.post("/flisr/simulate")
def flisr_simulate(body: FlisrRequest, _p=Depends(require_role(*EXEC_ROLES))):
    nodes = _load_nodes()
    edges = _load_edges()
    by_edge = {e["edge_id"]: e for e in edges}
    sources = _substations(nodes)

    # resolve fault location to a node.
    if body.fault_edge:
        if body.fault_edge not in by_edge:
            raise HTTPException(status_code=404, detail=f"unknown edge '{body.fault_edge}'")
        fault_node = by_edge[body.fault_edge]["to_node"]
    elif body.fault_node:
        if not any(n["node_id"] == body.fault_node for n in nodes):
            raise HTTPException(status_code=404, detail=f"unknown node '{body.fault_node}'")
        fault_node = body.fault_node
    else:
        raise HTTPException(status_code=422, detail="fault_node or fault_edge required")

    steps = [f"fault detected at {body.fault_edge or fault_node}"]
    before = _reach(edges, sources)

    # ISOLATE: nearest upstream switchable+closed edge whose subtree contains the fault.
    candidates = [e for e in edges if e["is_switchable"] and e["is_closed"]
                  and fault_node in _reach(edges, [e["to_node"]])]
    if not candidates:
        raise HTTPException(status_code=409, detail="no upstream switch can isolate this fault")
    iso = min(candidates, key=lambda e: len(_reach(edges, [e["to_node"]])))
    edges_iso = [{**e, "is_closed": False if e["edge_id"] == iso["edge_id"] else e["is_closed"]} for e in edges]
    steps.append(f"open switch {iso['edge_id']} to isolate {iso['to_node']}")
    after_iso = _reach(edges_iso, sources)
    lost = before - after_iso

    # RESTORE: close normally-open ties that re-feed lost load without re-energizing the fault.
    restored_edges, edges_cur = [], edges_iso
    for t in [e for e in edges_iso if not e["is_closed"]
              and (e["edge_type"] == "tie" or not e["normally_closed"])]:
        if t["to_node"] in lost or t["from_node"] in lost:
            trial = [{**e, "is_closed": True if e["edge_id"] == t["edge_id"] else e["is_closed"]}
                     for e in edges_cur]
            energ = _reach(trial, sources)
            if fault_node not in energ and (energ & lost):
                edges_cur = trial
                restored_edges.append(t["edge_id"])
                steps.append(f"close tie {t['edge_id']} to back-feed {t['to_node']}")

    after_restore = _reach(edges_cur, sources)
    restored = (after_restore - after_iso) - {fault_node}
    still_out = before - after_restore

    cust_lost = len(_service_points_in(lost))
    cust_restored = len(_service_points_in(restored))
    if not restored_edges:
        steps.append("no tie available to restore lost load — section remains out")

    # EXECUTE: persist the planned switch operations.
    if body.execute:
        common.execute("UPDATE grid_edges SET is_closed = FALSE WHERE edge_id = %s", (iso["edge_id"],))
        for eid in restored_edges:
            common.execute("UPDATE grid_edges SET is_closed = TRUE WHERE edge_id = %s", (eid,))
        steps.append("executed: switch states updated in network model")

    event_id = str(uuid.uuid4())
    result = {
        "event_id": event_id,
        "fault_node": fault_node,
        "fault_edge": body.fault_edge,
        "executed": body.execute,
        "isolated_edges": [iso["edge_id"]],
        "restored_edges": restored_edges,
        "customers_lost": cust_lost,
        "customers_restored": cust_restored,
        "customers_still_out": len(_service_points_in(still_out)),
        "steps": steps,
    }
    common.execute(
        "INSERT INTO flisr_events (event_id, fault_node, fault_edge, isolated_edges, restored_edges, "
        "customers_lost, customers_restored, executed, steps) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (event_id, fault_node, body.fault_edge, json.dumps([iso["edge_id"]]), json.dumps(restored_edges),
         cust_lost, cust_restored, body.execute, json.dumps(steps)),
    )
    return result


@router.get("/flisr/events")
def flisr_events(limit: int = 20, _p=Depends(require_role(*READ_ROLES))):
    limit = min(max(limit, 1), 100)
    return {"events": common.query_all(
        "SELECT * FROM flisr_events ORDER BY created_at DESC LIMIT %s", (limit,))}


# --- Volt/VAR ----------------------------------------------------------------
@router.get("/voltvar/recommendations")
def voltvar(_p=Depends(require_role(*READ_ROLES))):
    """Rule-based Volt/VAR: flag nodes outside band, recommend an action. Uses
    measured LV voltage where available, else the estimated per-unit voltage."""
    est = _estimate_state()
    recs = []
    for n in est:
        if not n["energized"]:
            continue
        mv = n["measured_voltage"]
        if mv is not None:
            if mv < VV_LV_LOW:
                recs.append(_rec(n, f"measured {mv} V < {VV_LV_LOW} V", "raise",
                                 "tap up / cap bank in or DER VAR support"))
            elif mv > VV_LV_HIGH:
                recs.append(_rec(n, f"measured {mv} V > {VV_LV_HIGH} V", "lower",
                                 "tap down / curtail DER export"))
        else:
            pu = n["estimated_voltage_pu"]
            if pu < VV_PU_LOW:
                recs.append(_rec(n, f"estimated {pu} pu < {VV_PU_LOW} pu", "raise",
                                 "tap up / cap bank in"))
            elif pu > VV_PU_HIGH:
                recs.append(_rec(n, f"estimated {pu} pu > {VV_PU_HIGH} pu", "lower",
                                 "tap down / curtail DER export"))
    return {
        "bands": {"lv_volts": [VV_LV_LOW, VV_LV_HIGH], "pu": [VV_PU_LOW, VV_PU_HIGH]},
        "violations": len(recs),
        "recommendations": recs,
        "note": "stub: rule-based on measured/estimated voltage; no closed-loop control.",
    }


def _rec(node: dict, issue: str, direction: str, action: str) -> dict:
    return {"node_id": node["node_id"], "name": node["name"], "issue": issue,
            "direction": direction, "recommended_action": action}
