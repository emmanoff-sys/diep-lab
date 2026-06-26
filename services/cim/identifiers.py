"""Deterministic CIM mRID / synthesized-ID generation -- one place so ID
schemes aren't duplicated across mapping modules.

CIM's mRID is meant to be a stable, globally-unique identifier. This
platform has no persistent mRID-allocation table, so mRIDs are
deterministically derived (uuid5 over a fixed namespace + the natural key)
rather than randomly generated on each call -- the same input always
yields the same mRID, which is what "identifiable" should mean for a
read-only adapter with no ID-allocation state of its own to persist.
"""
from __future__ import annotations

import uuid

# Fixed, arbitrary, constant namespace for this platform's CIM mRIDs -- so
# re-running mapping never changes an object's mRID.
_NAMESPACE = uuid.UUID("c1d00000-0000-0000-0000-000000000000")


def mrid_for(*parts: str) -> str:
    """Deterministic mRID (a UUID string) for a CIM object identified by
    `parts`, e.g. mrid_for("EndDevice", device_id)."""
    key = "/".join(str(p) for p in parts)
    return str(uuid.uuid5(_NAMESPACE, key))


def terminal_id(edge_id: str, sequence_number: int) -> str:
    """Two Terminals per grid_edges row -- sequence_number is 1 or 2."""
    return f"{edge_id}-T{sequence_number}"


def leaf_terminal_id(node_id: str) -> str:
    """One Terminal for a grid_nodes row with no edges referencing it."""
    return f"{node_id}-T1"


def usage_point_id(node_id: str | None, meter_device_id: str | None) -> str:
    """UsagePoint is deduplicated by (node_id, meter_device_id) -- see
    mapping/metering.py. meter_device_id is preferred as the key when
    present (more specific); falls back to node_id."""
    key = meter_device_id or node_id or "unknown"
    return f"UP-{key}"
