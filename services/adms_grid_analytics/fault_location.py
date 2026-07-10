"""DIEP ADMS P5-M6 — Fault Location.

Estimate where a fault is on a radial feeder, two complementary ways:

  * Impedance (reactance-to-fault): from a measured fault-current magnitude at the
    substation, find the section whose cumulative series impedance from the source
    produces that current for a bolted three-phase fault (I = V_ln / |Z_path|).
    Radial branching yields several candidates at similar distance — ranked by
    match error.
  * Topological (last-gasp): from the set of nodes/meters reporting loss of power,
    the fault is on the edge whose downstream subtree best matches that set.

When both inputs are present they reinforce: topology picks the faulted lateral,
impedance gives the distance along it. Pure functions over plain dicts; read-only.
"""

from __future__ import annotations

import math

from .state_estimation import SBASE_KW, build_radial


def _path_length_km(path_edges: list[dict]) -> float:
    return sum(float(e.get("length_km") or 0.0) for e in path_edges)


def locate(
    nodes: list[dict],
    edges: list[dict],
    fault_current_a: float | None = None,
    outage_nodes: list[str] | None = None,
    options: dict | None = None,
) -> dict:
    """Locate a fault from a measured fault current and/or outage-reporting nodes."""
    net = build_radial(nodes, edges)
    root, by_id, pu = net["root"], net["by_id"], net["pu"]
    path_edges, subtree, parent_edge = net["path_edges"], net["subtree"], net["parent_edge"]

    # --- impedance (reactance-to-fault) ranking ------------------------------
    # Per-unit cumulative impedance so the calc is valid across voltage levels
    # (the pilot spans 33→11→0.415 kV — summing raw ohms would be meaningless).
    # Bolted 3φ fault: I_pu = 1 / |Z_pu|, converted to amps at the faulted node's base.
    impedance_candidates = []
    if fault_current_a and fault_current_a > 0:
        for nid in net["order"]:
            if nid == root:
                continue
            zpu = 0j
            for e in path_edges[nid]:
                r, x = pu[e["edge_id"]]
                zpu += complex(r, x)
            zmag = abs(zpu)
            if zmag <= 1e-9:
                continue
            kv = float(by_id[nid].get("nominal_kv") or 0.415)
            i_base = SBASE_KW / (math.sqrt(3.0) * kv)
            i_est = (1.0 / zmag) * i_base
            err = abs(i_est - fault_current_a) / fault_current_a
            impedance_candidates.append(
                {
                    "section": parent_edge[nid]["edge_id"],
                    "to_node": nid,
                    "distance_km": round(_path_length_km(path_edges[nid]), 3),
                    "z_pu": round(zmag, 4),
                    "estimated_fault_current_a": round(i_est, 1),
                    "error_pct": round(100.0 * err, 1),
                }
            )
        impedance_candidates.sort(key=lambda c: c["error_pct"])

    # --- topological (last-gasp / outage report) -----------------------------
    topological = None
    if outage_nodes:
        oset = set(outage_nodes)
        best = None
        for nid in net["order"]:
            if nid == root:
                continue
            sub = subtree[parent_edge[nid]["edge_id"]]
            inter = len(sub & oset)
            union = len(sub | oset)
            jacc = inter / union if union else 0.0
            if best is None or jacc > best["score"]:
                best = {
                    "section": parent_edge[nid]["edge_id"],
                    "isolates_subtree": sorted(sub),
                    "score": round(jacc, 3),
                    "matches_report": sub == oset,
                }
        topological = best

    # --- combined best estimate ----------------------------------------------
    best_estimate = None
    if topological and topological.get("matches_report"):
        # narrow impedance candidates to the faulted lateral (within the subtree)
        sub = set(topological["isolates_subtree"])
        in_lateral = [c for c in impedance_candidates if c["to_node"] in sub]
        best_estimate = {
            "method": "topological+impedance",
            "section": topological["section"],
            "distance_km": (in_lateral[0]["distance_km"] if in_lateral else None),
        }
    elif impedance_candidates:
        best_estimate = {
            "method": "impedance",
            "section": impedance_candidates[0]["section"],
            "distance_km": impedance_candidates[0]["distance_km"],
        }
    elif topological:
        best_estimate = {
            "method": "topological",
            "section": topological["section"],
            "distance_km": None,
        }

    return {
        "method": "impedance reactance-to-fault + topological last-gasp",
        "inputs": {
            "fault_current_a": fault_current_a,
            "outage_nodes": sorted(outage_nodes) if outage_nodes else [],
        },
        "impedance_candidates": impedance_candidates[:5],
        "topological": topological,
        "best_estimate": best_estimate,
    }
