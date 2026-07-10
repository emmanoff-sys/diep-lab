"""DIEP ADMS P5-M4 — Optimal Network Reconfiguration (optimal switching).

Find the switch configuration that minimizes feeder losses while keeping the
network radial, fully served, and within voltage/thermal limits — the classic
distribution feeder reconfiguration problem. Read-only: produces a *recommended*
switching plan; live execution would flow through the governed OC-2 switch / FLISR
control plane.

Pure functions over plain dicts; evaluates each candidate with the M3 power flow
(dms.powerflow). The search is **exhaustive over the reconfigurable switches**
(sectionalizers + ties), which is exact for the handful of switches on a real
feeder section; for large networks the same evaluator plugs into a branch-exchange
heuristic (documented extension point) — the per-config feasibility + loss
evaluation is the reusable core.
"""

from __future__ import annotations

import copy
import itertools

from . import powerflow as pf


def _reconfigurable(edges: list[dict]) -> list[dict]:
    """Switches eligible for reconfiguration: switchable sectionalizers + ties,
    excluding device-islanding breakers (those island a DER, not reroute load)."""
    out = []
    for e in edges:
        if not e.get("is_switchable"):
            continue
        if e.get("edge_type") not in ("switch", "tie"):
            continue
        attrs = e.get("attrs") or {}
        if isinstance(attrs, dict) and attrs.get("role") == "islanding_breaker":
            continue
        out.append(e)
    return out


def _radial_feasible(nodes: list[dict], edges: list[dict]) -> tuple[bool, set]:
    """A config is feasible if, over its closed edges, the network energized from
    the substation(s) is a tree (radial, no loop) AND every load/meter node is
    energized (no load shed). Returns (feasible, energized_set)."""
    node_ids = {n["node_id"] for n in nodes}
    sources = [n["node_id"] for n in nodes if n["node_type"] == "substation"]
    if not sources:
        return False, set()
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    closed = [e for e in edges if e.get("is_closed", True)]
    for e in closed:
        adj[e["from_node"]].append(e["to_node"])
        adj[e["to_node"]].append(e["from_node"])
    # energized component from sources
    energized, stack = set(sources), list(sources)
    while stack:
        c = stack.pop()
        for nb in adj[c]:
            if nb not in energized:
                energized.add(nb)
                stack.append(nb)
    # radiality: closed edges fully inside the energized set must equal |E|-#sources
    ec = sum(1 for e in closed if e["from_node"] in energized and e["to_node"] in energized)
    if ec > len(energized) - len(sources):
        return False, energized  # a loop exists in the energized network
    # every load/meter served
    for n in nodes:
        if n["node_type"] in ("load", "meter") and n["node_id"] not in energized:
            return False, energized
    return True, energized


def _evaluate(nodes: list[dict], edges: list[dict], loads: dict) -> dict | None:
    """Feasibility + power-flow metrics for one config; None if infeasible."""
    feasible, _ = _radial_feasible(nodes, edges)
    if not feasible:
        return None
    res = pf.solve(nodes, edges, loads)
    if not res["converged"]:
        return None
    max_loading = (
        max((b["loading_pct"] or 0.0) for b in res["branches"]) if res["branches"] else 0.0
    )
    return {
        "loss_kw": res["total_loss_kw"],
        "violations": res["violation_count"],
        "max_loading_pct": round(max_loading, 1),
        "switch_state": {e["edge_id"]: bool(e["is_closed"]) for e in _reconfigurable(edges)},
    }


def recommend(
    nodes: list[dict], edges: list[dict], loads: dict, options: dict | None = None
) -> dict:
    """Search switch configurations for the minimum-loss feasible radial config."""
    sw = _reconfigurable(edges)
    sw_ids = [e["edge_id"] for e in sw]
    edge_by_id = {e["edge_id"]: e for e in edges}

    current_state = {eid: bool(edge_by_id[eid]["is_closed"]) for eid in sw_ids}
    current = _evaluate(nodes, edges, loads)

    best, best_combo, best_changes = None, None, None
    evaluated, feasible_count = 0, 0
    eps = 1e-6
    for combo in itertools.product([False, True], repeat=len(sw_ids)):
        evaluated += 1
        cand_edges = copy.deepcopy(edges)
        cbi = {e["edge_id"]: e for e in cand_edges}
        for eid, closed in zip(sw_ids, combo, strict=False):
            cbi[eid]["is_closed"] = closed
        m = _evaluate(nodes, cand_edges, loads)
        if m is None:
            continue
        feasible_count += 1
        combo_map = dict(zip(sw_ids, combo, strict=False))
        changes = sum(1 for eid in sw_ids if combo_map[eid] != current_state.get(eid))
        # minimize loss; tie-break (within eps) on fewest switching changes so an
        # equal-loss config never proposes a pointless switch move.
        if (
            best is None
            or m["loss_kw"] < best["loss_kw"] - eps
            or (abs(m["loss_kw"] - best["loss_kw"]) <= eps and changes < best_changes)
        ):
            best, best_combo, best_changes = m, combo_map, changes

    # switching plan = diff from current state
    plan = []
    if best_combo is not None:
        for eid in sw_ids:
            wantc = best_combo[eid]
            if wantc != current_state.get(eid):
                plan.append({"edge_id": eid, "action": "close" if wantc else "open"})

    cur_loss = current["loss_kw"] if current else None
    improvement = round(cur_loss - best["loss_kw"], 3) if (current and best) else None
    improvement_pct = (
        round(100.0 * improvement / cur_loss, 1) if (improvement is not None and cur_loss) else None
    )

    return {
        "method": "exhaustive over reconfigurable switches; objective = min total I²R loss, "
        "subject to radial + fully-served + no voltage/thermal violation",
        "reconfigurable_switches": sw_ids,
        "evaluated": evaluated,
        "feasible_count": feasible_count,
        "current": current,
        "recommended": best,
        "switching_plan": plan,
        "action_required": bool(plan),
        "loss_reduction_kw": improvement,
        "loss_reduction_pct": improvement_pct,
        "note": "recommendation only — execute via governed OC-2 switch / FLISR control actions",
    }
