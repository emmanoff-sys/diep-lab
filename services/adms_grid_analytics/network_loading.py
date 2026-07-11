"""DIEP ADMS P5-M11 — Network Loading Analytics (OA-131).

Deterministic loading analysis for radial distribution feeders. Consumes
power flow results from ``powerflow.solve()`` — no independent power flow
computation is performed here.

Feeder identification
---------------------
A feeder is defined as the subtree hanging from each direct branch of the
substation/source node. The feeder head edge connects the source to the
first load-side bus. All edges and nodes downstream of the feeder head
(inclusive) form the feeder extent.

Loading calculation
-------------------
Branch loading is taken directly from ``pf_result["branches"]``:
  - ampacity-based:  loading_pct = 100 × I_max / ampacity_a
  - rating-based:    loading_pct = 100 × S_total / rating_kw
  - unrated:         loading_pct = None (capacity unknown)

Source utilisation is derived from the sum of feeder head branch apparent
powers (S_kVA). No power flow is re-run; values are read from the result.
"""

from __future__ import annotations


def _source_id(nodes: list[dict]) -> str | None:
    return next((n["node_id"] for n in nodes if n.get("node_type") == "substation"), None)


def _build_children(nodes: list[dict], edges: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """Return parent → [(edge_id, child_node_id)] map via BFS from source.

    Only closed edges are traversed. Returns empty dict when no source found.
    Iteration order within each parent's child list is deterministic (sorted).
    """
    source = _source_id(nodes)
    if source is None:
        return {}
    all_ids = {n["node_id"] for n in nodes}
    adj: dict[str, list[tuple[str, str]]] = {nid: [] for nid in all_ids}
    for e in edges:
        if not e.get("is_closed", True):
            continue
        adj.setdefault(e["from_node"], []).append((e["edge_id"], e["to_node"]))
        adj.setdefault(e["to_node"], []).append((e["edge_id"], e["from_node"]))
    children: dict[str, list[tuple[str, str]]] = {nid: [] for nid in all_ids}
    seen = {source}
    queue = [source]
    while queue:
        cur = queue.pop(0)
        for eid, nbr in sorted(adj.get(cur, [])):
            if nbr not in seen:
                seen.add(nbr)
                children[cur].append((eid, nbr))
                queue.append(nbr)
    return children


def _subtree_edge_ids(root: str, children: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Return all edge_ids in the subtree below root (not including root's incoming edge)."""
    result: list[str] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        for eid, child in children.get(cur, []):
            result.append(eid)
            stack.append(child)
    return result


def _subtree_node_count(root: str, children: dict[str, list[tuple[str, str]]]) -> int:
    count, stack = 0, [root]
    while stack:
        cur = stack.pop()
        count += 1
        stack.extend(child for _, child in children.get(cur, []))
    return count


def feeder_loading(nodes: list[dict], edges: list[dict], pf_result: dict) -> list[dict]:
    """Return a per-feeder loading summary.

    Each entry describes one feeder — the subtree hanging from a direct branch
    of the source node. Feeders are sorted by peak_loading_pct descending
    (unrated feeders last).

    Returns:
        List of dicts with keys:
        ``feeder_head_edge``, ``feeder_root_node``, ``node_count``,
        ``branch_count``, ``total_s_kva``, ``peak_loading_pct``,
        ``avg_loading_pct``, ``total_loss_kw``.
    """
    source = _source_id(nodes)
    if source is None:
        return []
    children = _build_children(nodes, edges)
    branch_idx = {b["edge_id"]: b for b in pf_result.get("branches", [])}

    feeders: list[dict] = []
    for head_eid, feeder_root in children.get(source, []):
        downstream_eids = _subtree_edge_ids(feeder_root, children)
        all_eids = [head_eid] + downstream_eids
        total_loss_kw = 0.0
        loading_values: list[float] = []
        for eid in all_eids:
            b = branch_idx.get(eid, {})
            total_loss_kw += float(b.get("loss_kw") or 0.0)
            lp = b.get("loading_pct")
            if lp is not None:
                loading_values.append(float(lp))
        head_b = branch_idx.get(head_eid, {})
        peak = max(loading_values) if loading_values else None
        avg = round(sum(loading_values) / len(loading_values), 1) if loading_values else None
        feeders.append(
            {
                "feeder_head_edge": head_eid,
                "feeder_root_node": feeder_root,
                "node_count": _subtree_node_count(feeder_root, children),
                "branch_count": len(all_eids),
                "total_s_kva": round(float(head_b.get("s_kva") or 0.0), 2),
                "peak_loading_pct": round(peak, 1) if peak is not None else None,
                "avg_loading_pct": avg,
                "total_loss_kw": round(total_loss_kw, 3),
            }
        )
    feeders.sort(key=lambda f: (f["peak_loading_pct"] is None, -(f["peak_loading_pct"] or 0.0)))
    return feeders


def transformer_loading(pf_result: dict) -> list[dict]:
    """Return loading summary for all transformer branches in the PF result.

    Sorted by loading_pct descending (unrated transformers last).

    Returns:
        List of dicts with keys:
        ``edge_id``, ``from``, ``to``, ``s_kva``, ``loading_pct``,
        ``thermal_violation``.
    """
    result: list[dict] = []
    for b in pf_result.get("branches", []):
        if b.get("edge_type") != "transformer":
            continue
        lp = b.get("loading_pct")
        result.append(
            {
                "edge_id": b["edge_id"],
                "from": b["from"],
                "to": b["to"],
                "s_kva": b.get("s_kva"),
                "loading_pct": lp,
                "thermal_violation": lp is not None and float(lp) > 100.0,
            }
        )
    result.sort(key=lambda r: (r["loading_pct"] is None, -(r["loading_pct"] or 0.0)))
    return result


def source_loading(nodes: list[dict], pf_result: dict) -> dict:
    """Return source/substation utilisation metrics.

    Aggregates apparent power across all feeder head branches (those directly
    connected to the substation node).

    Returns:
        Dict with keys:
        ``source_id``, ``total_load_kva``, ``total_loss_kw``,
        ``converged``, ``feeder_count``.
    """
    source = _source_id(nodes)
    if source is None:
        return {
            "source_id": None,
            "total_load_kva": 0.0,
            "total_loss_kw": 0.0,
            "converged": False,
            "feeder_count": 0,
        }
    total_kva = 0.0
    total_loss = 0.0
    feeder_count = 0
    for b in pf_result.get("branches", []):
        if b.get("from") == source or b.get("to") == source:
            total_kva += float(b.get("s_kva") or 0.0)
            total_loss += float(b.get("loss_kw") or 0.0)
            feeder_count += 1
    return {
        "source_id": source,
        "total_load_kva": round(total_kva, 2),
        "total_loss_kw": round(total_loss, 3),
        "converged": bool(pf_result.get("converged", False)),
        "feeder_count": feeder_count,
    }


def utilisation_ranking(pf_result: dict) -> list[dict]:
    """Return all rated branches sorted by loading_pct descending.

    Only branches with a known loading_pct are included.

    Returns:
        List of dicts with keys:
        ``rank``, ``edge_id``, ``from``, ``to``, ``edge_type``,
        ``loading_pct``, ``loading_basis``, ``thermal_violation``.
    """
    rated = [b for b in pf_result.get("branches", []) if b.get("loading_pct") is not None]
    rated.sort(key=lambda b: -(float(b["loading_pct"])))
    return [
        {
            "rank": i + 1,
            "edge_id": b["edge_id"],
            "from": b["from"],
            "to": b["to"],
            "edge_type": b.get("edge_type"),
            "loading_pct": b["loading_pct"],
            "loading_basis": b.get("loading_basis"),
            "thermal_violation": float(b["loading_pct"]) > 100.0,
        }
        for i, b in enumerate(rated)
    ]


def loading_report(nodes: list[dict], edges: list[dict], pf_result: dict) -> dict:
    """Produce a combined network loading report.

    Returns:
        Dict with keys:
        ``feeders``, ``transformers``, ``source``, ``utilisation_ranking``,
        ``total_loss_kw``, ``violation_count``, ``converged``.
    """
    return {
        "feeders": feeder_loading(nodes, edges, pf_result),
        "transformers": transformer_loading(pf_result),
        "source": source_loading(nodes, pf_result),
        "utilisation_ranking": utilisation_ranking(pf_result),
        "total_loss_kw": pf_result.get("total_loss_kw"),
        "violation_count": pf_result.get("violation_count", 0),
        "converged": bool(pf_result.get("converged", False)),
    }
