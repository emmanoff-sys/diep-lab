"""Shared topology and analytical adaptation utilities (OA-129.5 / F-PAR003-05/06).

Consolidates topology snapshot conversion and SE-driven load derivation logic
previously duplicated across all four service modules into a single authoritative
implementation.

Dual-source reactive flow protocol (OA-129.2)
----------------------------------------------
SE branch q_kvar (LinearDistFlow model) is the authoritative source for reactive
flow SITING — it identifies where Q compensation is needed on the feeder.
PF node v_pu (three-phase BFS sweep) is the authoritative source for CONSTRAINT
VERIFICATION — it confirms voltage is within band after reactive dispatch.

Reactive device modelling protocol (OA-129.1 / OA-126)
--------------------------------------------------------
Capacitor banks and shunt compensation are modelled as negative-Q loads in the
loads dict consumed by the power flow engine:

    loads[node_id][phase] = complex(P_kw, -Q_injection_kvar / n_phases)

where Q_injection_kvar > 0 for capacitive (leading VAr injection into the network).
Inductive shunt reactors use Q_injection_kvar < 0 (positive Q load, absorbing VArs).

OLTC tap changes are represented by adjusting the nominal_kv of the regulated
node in the nodes list; the loads dict does not change with tap position.

The loads dict is the single point of entry for all reactive device state into
the power flow and contingency analysis engines.
"""

from __future__ import annotations

from typing import Any


def _phase_set(phases_str: str | None) -> list[str]:
    s = (phases_str or "ABC").lower()
    return [p for p in ("a", "b", "c") if p in s]


def nodes_edges_from_snapshot(
    snapshot: Any | None,
    topology_repository: Any | None = None,
) -> tuple[list[dict], list[dict]]:
    """Convert a WP-007 TopologySnapshot to engine-compatible plain dicts.

    If snapshot is None and topology_repository is provided, fetches the
    latest snapshot automatically. Shared by all four service modules as
    the canonical WP-007 adapter (OA-129.5).
    """
    if snapshot is None and topology_repository is not None:
        snapshot = topology_repository.get_latest()
    if snapshot is None:
        return [], []
    nodes = [
        {
            "node_id": n.node_id,
            "node_type": n.node_type,
            "name": n.name,
            "nominal_kv": n.nominal_kv,
            "phases": n.phases,
            "base_load_kw": float(n.attrs.get("base_load_kw") or 0.0),
            "base_load_kvar": float(n.attrs.get("base_load_kvar") or 0.0),
            "attrs": n.attrs,
        }
        for n in snapshot.nodes.values()
    ]
    edges = [
        {
            "edge_id": e.edge_id,
            "from_node": e.from_node,
            "to_node": e.to_node,
            "edge_type": e.edge_type,
            "is_closed": e.is_closed,
            "resistance_r_ohm": float(e.attrs.get("resistance_r_ohm") or 0.0),
            "reactance_x_ohm": float(e.attrs.get("reactance_x_ohm") or 0.0),
            "ampacity_a": e.attrs.get("ampacity_a"),
            "length_km": e.attrs.get("length_km"),
            "phases": e.phases,
            "is_switchable": bool(e.attrs.get("is_switchable", False)),
            "normally_closed": bool(e.attrs.get("normally_closed", True)),
            "attrs": e.attrs,
        }
        for e in snapshot.edges.values()
    ]
    return nodes, edges


def loads_from_se_result(se_result: dict, nodes: list[dict]) -> dict:
    """Derive per-phase complex load dict from SE node results (OA-129.5 / F-PAR003-06).

    Shared load derivation algorithm used by PowerFlowService,
    ContingencyAnalysisService, and VoltVARService. Converts each energised
    node's estimated_p_kw / estimated_q_kvar (balanced single-line equivalents)
    into the per-phase complex(P_kw, Q_kvar) format expected by the power flow
    engine. Load is distributed equally across the active phases of the node.

    Returns
    -------
    dict
        ``{node_id: {phase: complex(P_per_phase_kw, Q_per_phase_kvar)}}``
    """
    node_phases = {n["node_id"]: n.get("phases") for n in nodes}
    loads: dict[str, dict[str, complex]] = {}
    for se_node in se_result.get("nodes", []):
        if not se_node.get("energized", False):
            continue
        nid = se_node["node_id"]
        p = se_node.get("estimated_p_kw")
        q = float(se_node.get("estimated_q_kvar") or 0.0)
        if p is None:
            continue
        phases = _phase_set(node_phases.get(nid))
        if not phases:
            continue
        n_ph = len(phases)
        per_phase = complex(float(p) / n_ph, q / n_ph)
        loads[nid] = {ph: per_phase for ph in phases}
    return loads
