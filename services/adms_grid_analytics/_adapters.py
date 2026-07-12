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

# ------------------------------------------------------------------ #
# OA-140 — Boundary contract validation                               #
# ------------------------------------------------------------------ #


def validate_nodes_edges(nodes: object, edges: object) -> None:
    """Validate that nodes and edges satisfy the minimum contract shape.

    Checks performed:
    - ``nodes`` is a list (not None, not a dict, not a generator).
    - ``edges`` is a list.
    - Each node dict contains a non-empty string ``node_id``.
    - Each edge dict contains non-empty string keys ``edge_id``, ``from_node``,
      and ``to_node``.

    Raises
    ------
    TypeError
        If ``nodes`` or ``edges`` is not a list.
    ValueError
        If any node is missing ``node_id`` or any edge is missing a required key.
        The error message names the offending index and the missing field.

    Notes
    -----
    Empty lists are accepted — engines handle the empty-topology case gracefully.
    This validator does not enforce topology consistency (e.g. edge endpoints in
    the node set); that is the responsibility of ``StateEstimationService.
    validate_topology()``.
    """
    if not isinstance(nodes, list):
        raise TypeError(f"nodes must be a list, got {type(nodes).__name__}")
    if not isinstance(edges, list):
        raise TypeError(f"edges must be a list, got {type(edges).__name__}")
    for i, node in enumerate(nodes):
        nid = node.get("node_id") if isinstance(node, dict) else None
        if not nid or not isinstance(nid, str):
            raise ValueError(
                f"nodes[{i}] is missing a valid 'node_id' string field; "
                "each node must carry a non-empty unique string identifier"
            )
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"edges[{i}] is not a dict")
        for field in ("edge_id", "from_node", "to_node"):
            val = edge.get(field)
            if not val or not isinstance(val, str):
                raise ValueError(
                    f"edges[{i}] is missing a valid {field!r} string field; "
                    "each edge must carry non-empty 'edge_id', 'from_node', and 'to_node'"
                )


def validate_se_result(se_result: object) -> None:
    """Validate that an SE result satisfies the minimum EstimationResult contract shape.

    Checks performed:
    - ``se_result`` is a dict.
    - ``se_result["nodes"]`` is present and is a list.
    - Each node entry in ``se_result["nodes"]`` contains a non-empty ``node_id``.

    Raises
    ------
    TypeError
        If ``se_result`` is not a dict.
    ValueError
        If the ``nodes`` key is absent, not a list, or contains entries without
        a valid ``node_id``.
    """
    if not isinstance(se_result, dict):
        raise TypeError(
            f"se_result must be a dict (EstimationResult shape), got {type(se_result).__name__}"
        )
    if "nodes" not in se_result:
        raise ValueError(
            "se_result is missing the 'nodes' key; "
            "pass a result produced by StateEstimationService.estimate()"
        )
    se_nodes = se_result["nodes"]
    if not isinstance(se_nodes, list):
        raise ValueError(f"se_result['nodes'] must be a list, got {type(se_nodes).__name__}")
    for i, node in enumerate(se_nodes):
        nid = node.get("node_id") if isinstance(node, dict) else None
        if not nid or not isinstance(nid, str):
            raise ValueError(
                f"se_result['nodes'][{i}] is missing a valid 'node_id'; "
                "each SE node must carry a non-empty string identifier"
            )


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
