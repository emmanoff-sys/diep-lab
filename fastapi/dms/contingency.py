"""DIEP ADMS P5-M5 — N-1 Contingency Analysis.

For every credible single-element outage (each in-service line/transformer/switch),
simulate the element out, attempt FLISR-style restoration via available ties, run a
post-contingency power flow, and report unserved load, restored sections, and any
voltage/thermal violations — then rank contingencies by severity. Answers "is the
feeder N-1 secure, and if not, which single failures hurt and can we back-feed them?"

Pure functions over plain dicts; evaluates each post-contingency state with the M3
power flow (dms.powerflow) and a greedy radial tie-restoration that mirrors the
existing FLISR planner. Read-only.
"""
from __future__ import annotations

import copy

from . import powerflow as pf


def _energized(nodes: list[dict], edges: list[dict]) -> set:
    """Nodes reachable from substations over closed edges (undirected)."""
    node_ids = {n["node_id"] for n in nodes}
    sources = [n["node_id"] for n in nodes if n["node_type"] == "substation"]
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges:
        if e.get("is_closed", True):
            adj[e["from_node"]].append(e["to_node"])
            adj[e["to_node"]].append(e["from_node"])
    seen, stack = set(sources), list(sources)
    while stack:
        c = stack.pop()
        for nb in adj[c]:
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen


def _is_radial(nodes: list[dict], edges: list[dict], energized: set) -> bool:
    sources = [n["node_id"] for n in nodes if n["node_type"] == "substation"]
    ec = sum(1 for e in edges if e.get("is_closed", True)
             and e["from_node"] in energized and e["to_node"] in energized)
    return ec <= len(energized) - len(sources)


def _real_load_kw(loads: dict, node_id: str) -> float:
    """Net real power at a node (consumption +, DER generation −)."""
    return sum(v.real for v in loads.get(node_id, {}).values())


def _load_kw(loads: dict, node_id: str) -> float:
    """Customer load only (positive part) — ignores DER generation."""
    return max(_real_load_kw(loads, node_id), 0.0)


def _gen_kw(loads: dict, node_id: str) -> float:
    """DER generation only (magnitude of the negative part)."""
    return max(-_real_load_kw(loads, node_id), 0.0)


def _restore(nodes: list[dict], edges: list[dict], failed_eid: str,
             lost: set) -> list[str]:
    """Greedily close available open ties/switches to re-energize lost nodes without
    re-energizing through the failed element, keeping the network radial. Returns
    the list of switches closed."""
    closed_ties: list[str] = []
    openable = [e for e in edges if not e.get("is_closed", True) and e.get("is_switchable")
                and e["edge_id"] != failed_eid]
    progress = True
    while progress and lost:
        progress = False
        for e in openable:
            if e["edge_id"] in closed_ties:
                continue
            # try closing this tie
            e["is_closed"] = True
            energ = _energized(nodes, edges)
            if (lost & energ) and _is_radial(nodes, edges, energ):
                closed_ties.append(e["edge_id"])
                lost = lost - energ
                progress = True
            else:
                e["is_closed"] = False  # revert
    return closed_ties


def analyze(nodes: list[dict], edges: list[dict], loads: dict,
            customers_by_node: dict | None = None, options: dict | None = None,
            load_floor: dict | None = None) -> dict:
    """Run N-1 over every in-service line/transformer/switch element.

    `load_floor` (optional) maps node_id → a fallback real load (kW) used ONLY in the
    load-based classification sums (lost/unserved load), not in the power flow. It
    exists for meters whose live telemetry reads ~0 because they are in AMI last-gasp:
    without it, losing such a meter looks like "no load lost" (secure) even though
    customers are out. The floor restores the customer-load reality to the
    classification without otherwise changing ranking."""
    customers_by_node = customers_by_node or {}
    load_floor = load_floor or {}
    base_energized = _energized(nodes, edges)
    base = pf.solve(nodes, edges, loads)

    def customers(node_set) -> int:
        return sum(customers_by_node.get(n, 0) for n in node_set)

    def classif_load(n: str) -> float:
        """Real load for classification: the live load, floored by any fallback."""
        return max(_load_kw(loads, n), float(load_floor.get(n, 0.0)))

    candidates = [e for e in edges if e.get("is_closed", True)
                  and e["edge_type"] in ("line", "transformer", "switch", "tie")]

    results = []
    for ce in candidates:
        ed = copy.deepcopy(edges)
        cbi = {e["edge_id"]: e for e in ed}
        cbi[ce["edge_id"]]["is_closed"] = False  # element out
        after_out = _energized(nodes, ed)
        lost = base_energized - after_out
        lost_load = round(sum(classif_load(n) for n in lost), 2)
        lost_gen = round(sum(_gen_kw(loads, n) for n in lost), 2)
        lost_customers = customers(lost)  # pre-restoration (M8 cross-check)

        restored_by = _restore(nodes, ed, ce["edge_id"], set(lost))
        after_restore = _energized(nodes, ed)
        still_out = base_energized - after_restore
        unserved_nodes = [n for n in still_out if classif_load(n) > 0
                          or customers_by_node.get(n, 0) > 0]
        unserved_load = round(sum(classif_load(n) for n in still_out), 2)
        unserved_cust = customers(still_out)

        # post-contingency power flow (post-restoration network)
        pfres = pf.solve(nodes, ed, loads)
        violations = pfres["violation_count"]

        if unserved_load > 0:
            cls = "unserved" if not restored_by else "partial"
        elif violations > 0:
            cls = "violation"  # service kept but a voltage/thermal limit is breached
        else:
            cls = "restorable" if restored_by else "secure"
        severity = unserved_load * 1000 + violations * 100 + (lost_load if restored_by else 0)

        results.append({
            "element": ce["edge_id"], "element_type": ce["edge_type"],
            "lost_load_kw": lost_load, "lost_generation_kw": lost_gen,
            "lost_customers": lost_customers,
            "restored_by": restored_by,
            "unserved_load_kw": unserved_load,
            "unserved_customers": unserved_cust,
            "unserved_nodes": sorted(unserved_nodes),
            "post_violations": violations,
            "converged": pfres["converged"],
            "classification": cls,
            "severity": round(severity, 2),
        })

    results.sort(key=lambda r: r["severity"], reverse=True)
    n1_secure = all(r["unserved_load_kw"] == 0 and r["post_violations"] == 0
                    for r in results)
    return {
        "method": "N-1 over in-service elements; greedy radial tie-restoration; "
                  "post-contingency three-phase power flow",
        "base_case": {"converged": base["converged"], "loss_kw": base["total_loss_kw"],
                      "violations": base["violation_count"]},
        "n1_secure": n1_secure,
        "contingencies_evaluated": len(results),
        "worst": results[:5],
        "contingencies": results,
    }
