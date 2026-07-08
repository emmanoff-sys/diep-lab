"""WP-006-04 — pure payload validation for POST /topology/versions.

Stdlib-only over plain dicts (no pydantic, no psycopg2) so it is importable
in the python-only unit validation profile — the same pure-logic/router
split fastapi/readiness.py uses (tests/test_topology_publish_unit.py).

Checks *internal* payload consistency only: required keys, duplicate ids,
self-loop edges, and cross-references that can be resolved within the
payload itself. References that may legitimately resolve against rows
already in the database (an edge endpoint or parent_id naming an existing
node that is not re-sent in this payload) are deliberately NOT rejected
here — the grid_nodes/grid_edges foreign keys are authoritative for those,
and the router surfaces FK violations as 409. Enum values (node_type,
edge_type) are likewise left to the sql/013 CHECK constraints rather than
duplicating the allowed lists in Python, so the schema cannot drift from
this validator.
"""
from __future__ import annotations

__all__ = ["validate_publish_payload"]


def validate_publish_payload(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Return a list of human-readable payload errors; empty means valid."""
    errors: list[str] = []

    seen_nodes: set[str] = set()
    for i, n in enumerate(nodes):
        node_id = n.get("node_id")
        if not node_id:
            errors.append(f"nodes[{i}]: node_id is required")
            continue
        if node_id in seen_nodes:
            errors.append(f"nodes[{i}]: duplicate node_id '{node_id}'")
        seen_nodes.add(node_id)
        if not n.get("node_type"):
            errors.append(f"nodes[{i}] ('{node_id}'): node_type is required")

    seen_edges: set[str] = set()
    for i, e in enumerate(edges):
        edge_id = e.get("edge_id")
        if not edge_id:
            errors.append(f"edges[{i}]: edge_id is required")
            continue
        if edge_id in seen_edges:
            errors.append(f"edges[{i}]: duplicate edge_id '{edge_id}'")
        seen_edges.add(edge_id)
        frm, to = e.get("from_node"), e.get("to_node")
        if not frm or not to:
            errors.append(f"edges[{i}] ('{edge_id}'): from_node and to_node are required")
            continue
        if frm == to:
            errors.append(f"edges[{i}] ('{edge_id}'): self-loop ({frm} -> {to})")

    return errors
