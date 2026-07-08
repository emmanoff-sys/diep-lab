"""WP-006-05 — pure logic for the topology version history & diff API.

Stdlib-only over plain dicts (no pydantic, no psycopg2) so it is importable
in the python-only unit validation profile — the same pure-logic/router
split fastapi/readiness.py and fastapi/topology_publish.py use
(tests/test_topology_history_unit.py).

SEMANTICS (AR-054 finding F-AR054-02, recorded as WP-006-05 scoping input):
grid_nodes/grid_edges carry the model_version that LAST WROTE each row —
the schema stamps writes, it does not snapshot states. Consequently:
  * "diff from A to B" means: rows whose current content was last written
    by a version in (A, B] — i.e. what those publishes touched;
  * values a row held before its latest write are not reconstructable;
  * rows deleted between versions are invisible to the diff.
Every diff response carries `"semantics": "write-stamp"` so clients cannot
mistake this for snapshot reconstruction.
"""
from __future__ import annotations

__all__ = ["DIFF_SEMANTICS", "validate_diff_range", "summarize_diff"]

DIFF_SEMANTICS = "write-stamp"


def validate_diff_range(from_version: int, to_version: int) -> list[str]:
    """Return human-readable parameter errors; empty means valid.

    Existence of the versions is the router's concern (it holds the DB);
    this validates only the shape of the requested range.
    """
    errors: list[str] = []
    if from_version < 1:
        errors.append(f"from_version must be >= 1 (got {from_version})")
    if to_version < 1:
        errors.append(f"to_version must be >= 1 (got {to_version})")
    if not errors and from_version >= to_version:
        errors.append(
            f"from_version ({from_version}) must be lower than to_version ({to_version})"
        )
    return errors


def summarize_diff(
    versions_in_range: list[dict],
    nodes: list[dict],
    edges: list[dict],
) -> dict:
    """Assemble the diff payload with per-version touch counts.

    `versions_in_range` are network_model_versions rows with version > from
    and version <= to; `nodes`/`edges` are the grid rows stamped by those
    versions. Rows are grouped by the version that last wrote them.
    """
    per_version: dict[int, dict[str, int]] = {
        v["version"]: {"nodes_touched": 0, "edges_touched": 0} for v in versions_in_range
    }
    for n in nodes:
        counts = per_version.get(n["model_version"])
        if counts is not None:
            counts["nodes_touched"] += 1
    for e in edges:
        counts = per_version.get(e["model_version"])
        if counts is not None:
            counts["edges_touched"] += 1

    return {
        "semantics": DIFF_SEMANTICS,
        "versions_in_range": [
            {**v, **per_version[v["version"]]} for v in versions_in_range
        ],
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "versions": len(versions_in_range),
            "nodes_touched": len(nodes),
            "edges_touched": len(edges),
        },
    }
