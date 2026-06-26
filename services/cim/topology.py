"""Feeder/transformer ancestry walk for CIM mapping -- reuses the exact
same parent_id-walk logic as services/mdm/enrichment.py's
DeviceMetadataEnricher._walk_to_node_type (same query shape, same
max_hops=10 default) rather than reinventing it: this exact problem is
already solved and validated there, and CIM and MDM should agree on a
device's feeder/transformer ancestry since both read the same
grid_nodes table.
"""
from __future__ import annotations

from . import db

MAX_HOPS = 10


def _fetch_grid_node(node_id: str) -> dict | None:
    return db.query_one(
        "SELECT node_id, node_type, parent_id FROM grid_nodes "
        "WHERE node_id = %s OR device_id = %s",
        (node_id, node_id),
    )


def walk_to_node_type(start_id: str, target_type: str, max_hops: int = MAX_HOPS,
                       node_fetcher=None) -> str | None:
    """Walks grid_nodes.parent_id upward from start_id (a node_id or
    device_id) to the nearest ancestor with node_type == target_type.
    Returns None if the model doesn't reach that far -- an honest "not
    modeled yet" gap, never a fabricated value (same discipline as
    services/mdm/enrichment.py)."""
    fetch = node_fetcher or _fetch_grid_node
    node = fetch(start_id)
    for _ in range(max_hops):
        if node is None:
            return None
        if node["node_type"] == target_type:
            return node["node_id"]
        parent_id = node.get("parent_id")
        if not parent_id:
            return None
        node = fetch(parent_id)
    return None


def feeder_and_transformer_for(start_id: str, node_fetcher=None) -> tuple[str | None, str | None]:
    return (
        walk_to_node_type(start_id, "feeder", node_fetcher=node_fetcher),
        walk_to_node_type(start_id, "transformer", node_fetcher=node_fetcher),
    )
