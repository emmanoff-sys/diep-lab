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

import math

import common
from auth import require_role
from routers.controls import controls_enabled  # OC-3: gate legacy execute=true on the master flag
from dms import state_estimation as se  # P5-M2 WLS estimator (pure engine)
from dms import powerflow as pf  # P5-M3 three-phase power flow (pure engine)
from dms import reconfiguration as rc  # P5-M4 optimal switching (pure engine)
from dms import contingency as ct  # P5-M5 N-1 contingency analysis (pure engine)
from dms import fault_location as flc  # P5-M6 fault location (pure engine)

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


def plan_flisr(fault_node_arg: str | None = None, fault_edge_arg: str | None = None) -> dict:
    """Pure FLISR planner over the M1 graph — isolate the fault at the nearest
    upstream switch, restore lost load via a normally-open tie without
    re-energizing the fault. No mutation. Reused by /dms/flisr/simulate and the
    governed OC-3 `flisr` control action. Raises HTTPException on bad input or
    when no isolation is possible."""
    nodes = _load_nodes()
    edges = _load_edges()
    by_edge = {e["edge_id"]: e for e in edges}
    sources = _substations(nodes)

    if fault_edge_arg:
        if fault_edge_arg not in by_edge:
            raise HTTPException(status_code=404, detail=f"unknown edge '{fault_edge_arg}'")
        fault_node = by_edge[fault_edge_arg]["to_node"]
    elif fault_node_arg:
        if not any(n["node_id"] == fault_node_arg for n in nodes):
            raise HTTPException(status_code=404, detail=f"unknown node '{fault_node_arg}'")
        fault_node = fault_node_arg
    else:
        raise HTTPException(status_code=422, detail="fault_node or fault_edge required")

    steps = [f"fault detected at {fault_edge_arg or fault_node}"]
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
    if not restored_edges:
        steps.append("no tie available to restore lost load — section remains out")

    return {
        "fault_node": fault_node,
        "fault_edge": fault_edge_arg,
        "isolated_edge": iso["edge_id"],
        "isolated_edges": [iso["edge_id"]],
        "restored_edges": restored_edges,
        "customers_lost": len(_service_points_in(lost)),
        "customers_restored": len(_service_points_in(restored)),
        "customers_still_out": len(_service_points_in(still_out)),
        "still_out_nodes": sorted(still_out),
        "steps": steps,
        # pre-FLISR switch state, for governed rollback: iso was closed, ties were open.
        "before_switch_state": {iso["edge_id"]: True, **{eid: False for eid in restored_edges}},
    }


@router.post("/flisr/simulate")
def flisr_simulate(body: FlisrRequest, _p=Depends(require_role(*EXEC_ROLES))):
    plan = plan_flisr(body.fault_node, body.fault_edge)
    steps = list(plan["steps"])

    # EXECUTE: legacy direct path. As of OC-3 this ungoverned mutation is gated on
    # the master flag; the sanctioned live path is the governed /controls `flisr`
    # action (request -> two-person approve -> execute -> audit -> rollback).
    if body.execute:
        if not controls_enabled():
            raise HTTPException(status_code=403,
                                detail="live FLISR execution requires OC_CONTROLS_ENABLED; "
                                       "use the governed /controls flisr action")
        common.execute("UPDATE grid_edges SET is_closed = FALSE WHERE edge_id = %s", (plan["isolated_edge"],))
        for eid in plan["restored_edges"]:
            common.execute("UPDATE grid_edges SET is_closed = TRUE WHERE edge_id = %s", (eid,))
        steps.append("executed: switch states updated in network model")

    event_id = str(uuid.uuid4())
    result = {
        "event_id": event_id,
        "fault_node": plan["fault_node"],
        "fault_edge": body.fault_edge,
        "executed": body.execute,
        "isolated_edges": plan["isolated_edges"],
        "restored_edges": plan["restored_edges"],
        "customers_lost": plan["customers_lost"],
        "customers_restored": plan["customers_restored"],
        "customers_still_out": plan["customers_still_out"],
        "steps": steps,
    }
    common.execute(
        "INSERT INTO flisr_events (event_id, fault_node, fault_edge, isolated_edges, restored_edges, "
        "customers_lost, customers_restored, executed, steps, network_model_version) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (event_id, plan["fault_node"], body.fault_edge, json.dumps(plan["isolated_edges"]),
         json.dumps(plan["restored_edges"]), plan["customers_lost"], plan["customers_restored"],
         body.execute, json.dumps(steps), common.current_model_version()),
    )
    return result


@router.get("/flisr/events")
def flisr_events(limit: int = 20, _p=Depends(require_role(*READ_ROLES))):
    limit = min(max(limit, 1), 100)
    return {"events": common.query_all(
        "SELECT * FROM flisr_events ORDER BY created_at DESC LIMIT %s", (limit,))}


# --- Volt/VAR ----------------------------------------------------------------
def voltvar_recommendations() -> dict:
    """Pure rule-based Volt/VAR: flag energized nodes outside band and recommend a
    direction. Uses measured LV voltage where available, else the estimated per-unit
    voltage. Reused by the /voltvar/recommendations endpoint and the P4-3 continuous
    Volt/VAR automation policy (which closes the loop the note below describes)."""
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
        "note": "rule-based on measured/estimated voltage; P4-3 closes the loop via governed DER dispatch.",
    }


@router.get("/voltvar/recommendations")
def voltvar(_p=Depends(require_role(*READ_ROLES))):
    return voltvar_recommendations()


def _rec(node: dict, issue: str, direction: str, action: str) -> dict:
    return {"node_id": node["node_id"], "name": node["name"], "issue": issue,
            "direction": direction, "recommended_action": action}


# --- P5-M2: WLS Distribution State Estimation ---------------------------------
# This is the utility-grade successor to the /dms/state_estimation stub above:
# a real weighted-least-squares estimator (fastapi/dms/state_estimation.py) over
# the P5-M1 electrical model. The stub endpoint is retained for backwards
# compatibility; new clients use /dms/se/estimate.
def _se_nodes() -> list[dict]:
    return common.query_all(
        "SELECT node_id, node_type, name, nominal_kv, base_load_kw, base_load_kvar, phases "
        "FROM grid_nodes")


def _se_edges() -> list[dict]:
    return common.query_all(
        "SELECT edge_id, from_node, to_node, edge_type, is_switchable, is_closed, "
        "normally_closed, resistance_r_ohm, reactance_x_ohm, ampacity_a, rating_kw, "
        "phases, attrs FROM grid_edges")


def _se_measurements(nodes: list[dict]) -> dict:
    """Build the estimator's measurement dict from fresh telemetry on device-linked
    nodes. Net-load convention (consumption positive); voltage converted to per-unit
    on each node's phase-voltage base (nominal_kv·1000/√3)."""
    dev_rows = common.query_all(
        "SELECT DISTINCT ON (device_id) device_id, voltage, power_kw, grid_import_kw, "
        "EXTRACT(EPOCH FROM (now() - time)) AS age FROM telemetry ORDER BY device_id, time DESC")
    fresh = {r["device_id"]: r for r in dev_rows
             if r["age"] is not None and float(r["age"]) <= TELEMETRY_FRESH_S}
    node_dev = common.query_all("SELECT node_id, device_id, nominal_kv FROM grid_nodes "
                                "WHERE device_id IS NOT NULL")
    meas: dict = {}
    for nd in node_dev:
        r = fresh.get(nd["device_id"])
        if not r:
            continue
        m: dict = {}
        p = r.get("grid_import_kw")
        if p is None:
            p = r.get("power_kw")
        if p is not None:
            m["p_kw"] = float(p)
        v = r.get("voltage")
        kv = nd.get("nominal_kv")
        if v is not None and kv:
            base_v = float(kv) * 1000.0 / math.sqrt(3.0)
            if base_v > 0:
                m["voltage_pu"] = round(float(v) / base_v, 4)
        if m:
            meas[nd["node_id"]] = m
    return meas


@router.get("/se/estimate")
def se_estimate(_p=Depends(require_role(*READ_ROLES))):
    nodes = _se_nodes()
    edges = _se_edges()
    meas = _se_measurements(nodes)
    try:
        result = se.estimate(nodes, edges, meas)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"state estimation failed: {exc}")
    result["monitored_nodes"] = sum(1 for n in result["nodes"] if n.get("monitored"))
    result["telemetry_inputs"] = len(meas)
    return result


# --- P5-M3: Unbalanced (three-phase) Power Flow -------------------------------
def _phase_list(s: str | None) -> list[str]:
    s = (s or "ABC").lower()
    return [p for p in ("a", "b", "c") if p in s]


def _pf_loads(nodes: list[dict]) -> dict:
    """Per-node, per-phase complex load (kW + j·kvar) for the power flow. Net-load
    convention (consumption +, DER generation −). Real load comes from fresh
    telemetry where available, else the M1 base load; balanced load splits evenly
    across the node's phases, single-phase laterals keep all load on their phase."""
    dev_rows = common.query_all(
        "SELECT DISTINCT ON (device_id) device_id, power_kw, grid_import_kw, "
        "EXTRACT(EPOCH FROM (now() - time)) AS age FROM telemetry ORDER BY device_id, time DESC")
    fresh = {r["device_id"]: r for r in dev_rows
             if r["age"] is not None and float(r["age"]) <= TELEMETRY_FRESH_S}
    dev_by_node = {r["node_id"]: r["device_id"] for r in
                   common.query_all("SELECT node_id, device_id FROM grid_nodes "
                                    "WHERE device_id IS NOT NULL")}
    loads: dict = {}
    for n in nodes:
        nid = n["node_id"]
        phases = _phase_list(n.get("phases"))
        if not phases:
            continue
        p_kw = float(n.get("base_load_kw") or 0.0)
        q_kvar = float(n.get("base_load_kvar") or 0.0)
        dev = dev_by_node.get(nid)
        r = fresh.get(dev) if dev else None
        if r is not None:
            if n["node_type"] == "der":
                # DER telemetry power is generation → negative load
                p_kw = -float(r.get("power_kw") or 0.0)
            else:
                gi = r.get("grid_import_kw")
                p_kw = float(gi if gi is not None else (r.get("power_kw") or 0.0))
        per = len(phases)
        loads[nid] = {ph: complex(p_kw / per, q_kvar / per) for ph in phases}
    return loads


@router.get("/powerflow/solve")
def powerflow_solve(_p=Depends(require_role(*READ_ROLES))):
    nodes = _se_nodes()
    edges = _se_edges()
    loads = _pf_loads(nodes)
    try:
        result = pf.solve(nodes, edges, loads)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"power flow failed: {exc}")
    return result


# --- P5-M4: Optimal Network Reconfiguration (optimal switching) ---------------
@router.get("/reconfiguration/recommend")
def reconfiguration_recommend(_p=Depends(require_role(*READ_ROLES))):
    nodes = _se_nodes()
    edges = _se_edges()
    loads = _pf_loads(nodes)
    try:
        return rc.recommend(nodes, edges, loads)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"reconfiguration failed: {exc}")


# --- P5-M5: N-1 Contingency Analysis ------------------------------------------
def _customers_by_node() -> dict:
    rows = common.query_all(
        "SELECT node_id, COUNT(*) AS n FROM service_points WHERE node_id IS NOT NULL "
        "GROUP BY node_id")
    return {r["node_id"]: int(r["n"]) for r in rows}


def _lastgasp_load_floor() -> dict:
    """Fallback real load (kW) for meter nodes whose latest telemetry is AMI
    last-gasp — their live reading is ~0, so M5's load-based classification uses
    their M1 base load instead of treating the outage as 'secure'."""
    rows = common.query_all(
        "SELECT n.node_id, n.base_load_kw FROM grid_nodes n JOIN "
        "(SELECT DISTINCT ON (device_id) device_id, state FROM telemetry "
        " ORDER BY device_id, time DESC) t ON t.device_id = n.device_id "
        "WHERE upper(coalesce(t.state, '')) = 'LAST_GASP' AND n.base_load_kw > 0")
    return {r["node_id"]: float(r["base_load_kw"]) for r in rows}


@router.get("/contingency/n1")
def contingency_n1(_p=Depends(require_role(*READ_ROLES))):
    nodes = _se_nodes()
    edges = _se_edges()
    loads = _pf_loads(nodes)
    try:
        return ct.analyze(nodes, edges, loads, _customers_by_node(),
                          load_floor=_lastgasp_load_floor())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"contingency analysis failed: {exc}")


# --- P5-M6: Fault Location -----------------------------------------------------
class FaultLocateRequest(BaseModel):
    fault_current_a: float | None = Field(None, examples=[800.0])
    outage_nodes: list[str] | None = Field(None, examples=[["BUS-01", "ND-METER001"]])


@router.post("/fault_location/locate")
def fault_location_locate(body: FaultLocateRequest, _p=Depends(require_role(*READ_ROLES))):
    if not body.fault_current_a and not body.outage_nodes:
        raise HTTPException(status_code=422,
                            detail="provide fault_current_a and/or outage_nodes")
    nodes = _se_nodes()
    edges = _se_edges()
    try:
        return flc.locate(nodes, edges, fault_current_a=body.fault_current_a,
                          outage_nodes=body.outage_nodes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"fault location failed: {exc}")
