"""DIEP ADMS P5-M11 — Capacity and Constraint Analysis (OA-132).

Deterministic capacity calculations for distribution network assets.
Consumes power flow results — no independent computation is performed.

Remaining capacity
------------------
For each rated branch: remaining_pct = 100 − loading_pct.
For unrated branches: remaining_pct is None (no known rating).

Bottlenecks
-----------
Branches loaded at or above a configurable threshold (default 80 %) are
classified as bottlenecks.  Overloaded branches (> 100 %) are a special
case; their ``severity`` is ``"critical"`` rather than ``"warning"``.
"""

from __future__ import annotations


def remaining_capacity(pf_result: dict) -> list[dict]:
    """Return remaining capacity for every rated branch.

    Sorted by remaining_pct ascending — most constrained assets first.
    Unrated branches (loading_pct is None) are excluded.

    Returns:
        List of dicts with keys:
        ``edge_id``, ``from``, ``to``, ``edge_type``,
        ``loading_pct``, ``remaining_pct``, ``overloaded``.
    """
    result: list[dict] = []
    for b in pf_result.get("branches", []):
        lp = b.get("loading_pct")
        if lp is None:
            continue
        loading = float(lp)
        result.append(
            {
                "edge_id": b["edge_id"],
                "from": b["from"],
                "to": b["to"],
                "edge_type": b.get("edge_type"),
                "loading_pct": lp,
                "remaining_pct": round(100.0 - loading, 1),
                "overloaded": loading > 100.0,
            }
        )
    result.sort(key=lambda r: r["remaining_pct"])
    return result


def bottlenecks(pf_result: dict, threshold_pct: float = 80.0) -> list[dict]:
    """Return branches loaded at or above threshold_pct.

    Sorted by loading_pct descending (most loaded first).

    Args:
        pf_result: Power flow result dict.
        threshold_pct: Loading percentage threshold (default 80.0).

    Returns:
        List of dicts with keys:
        ``edge_id``, ``from``, ``to``, ``edge_type``,
        ``loading_pct``, ``remaining_pct``, ``overloaded``, ``severity``.
    """
    result: list[dict] = []
    for b in pf_result.get("branches", []):
        lp = b.get("loading_pct")
        if lp is None:
            continue
        loading = float(lp)
        if loading < threshold_pct:
            continue
        result.append(
            {
                "edge_id": b["edge_id"],
                "from": b["from"],
                "to": b["to"],
                "edge_type": b.get("edge_type"),
                "loading_pct": lp,
                "remaining_pct": round(100.0 - loading, 1),
                "overloaded": loading > 100.0,
                "severity": "critical" if loading > 100.0 else "warning",
            }
        )
    result.sort(key=lambda r: -(float(r["loading_pct"])))
    return result


def capacity_summary(nodes: list[dict], edges: list[dict], pf_result: dict) -> dict:
    """Return a network-wide capacity summary.

    Returns:
        Dict with keys:
        ``total_branches``, ``rated_branches``, ``unrated_branches``,
        ``overloaded_count``, ``near_limit_count`` (80–100 %),
        ``spare_count`` (< 80 %), ``headroom_pct``
        (minimum remaining capacity across rated branches, or None if none
        are rated), ``most_constrained_edge``.
    """
    branches = pf_result.get("branches", [])
    total = len(branches)
    rated = [b for b in branches if b.get("loading_pct") is not None]

    overloaded = sum(1 for b in rated if float(b["loading_pct"]) > 100.0)
    near_limit = sum(1 for b in rated if 80.0 <= float(b["loading_pct"]) <= 100.0)
    spare = sum(1 for b in rated if float(b["loading_pct"]) < 80.0)

    remaining_values = [100.0 - float(b["loading_pct"]) for b in rated]
    headroom = min(remaining_values) if remaining_values else None
    most_constrained: str | None = None
    if rated:
        worst = max(rated, key=lambda b: float(b["loading_pct"]))
        most_constrained = worst["edge_id"]

    return {
        "total_branches": total,
        "rated_branches": len(rated),
        "unrated_branches": total - len(rated),
        "overloaded_count": overloaded,
        "near_limit_count": near_limit,
        "spare_count": spare,
        "headroom_pct": round(headroom, 1) if headroom is not None else None,
        "most_constrained_edge": most_constrained,
    }
