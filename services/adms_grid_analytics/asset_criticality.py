"""DIEP ADMS P5-M11 — Asset Criticality Engine (OA-133).

Deterministic 4-dimension weighted ranking of distribution network assets.
All scores are normalised to [0, 1] before applying weights; the composite
``criticality_score`` is also in [0, 1].

Dimensions
----------
topology    (w=0.25)  Structural importance: downstream node count / total
                      energised node count.  A feeder head that serves all
                      downstream buses scores close to 1.0.

loading     (w=0.35)  Thermal stress: min(loading_pct / 100, 1.0).
                      Unrated branches score 0.0 for this dimension.

contingency (w=0.30)  Fault severity: proportion of this element's worst
                      severity relative to the maximum severity observed
                      across all contingencies. When ca_result is not
                      supplied, all branches score 0.0 and the
                      contingency weight redistributes to the others.

customer    (w=0.10)  Customer impact: downstream customers / total
                      customers. When customers_by_node is not supplied,
                      all branches score 0.0 and the customer weight
                      redistributes to the others.

Inactive dimension redistribution (OA-141 / R-PAR004-06)
---------------------------------------------------------
When one or more dimensions cannot be scored (``ca_result`` absent removes
``contingency``; ``customers_by_node`` absent removes ``customer``), their
weights are *not* applied. The remaining active dimensions are re-normalised
so they still sum to 1.0:

    active_weight[dim] = raw_weight[dim] / sum(raw_weight[d] for d in active_dims)

For example, with default weights ``{topology: 0.25, loading: 0.35,
contingency: 0.30, customer: 0.10}`` and both ``ca_result`` and
``customers_by_node`` absent (only topology + loading active):

    active_weight[topology] = 0.25 / (0.25 + 0.35) ≈ 0.417
    active_weight[loading]  = 0.35 / (0.25 + 0.35) ≈ 0.583

Custom weights passed via ``weights=`` are merged with the defaults first,
then the same normalisation is applied to the active subset. A caller
that passes ``weights={"topology": 1.0, "loading": 0.0}`` with no CA result
will get ``{topology: 1.0, loading: 0.0}`` after normalisation (loading
contributes nothing but is still active; contingency and customer are absent
and redistributed into the existing topology/loading split).

If all active-dimension weights sum to zero (only possible when a caller
explicitly zeroes every active dimension), weights are redistributed equally
across active dimensions to avoid a zero-divisor. This is an edge case; the
default weights never produce it.

Ranking
-------
Ties are broken deterministically by edge_id (lexicographic, ascending).
"""

from __future__ import annotations

_DEFAULT_WEIGHTS: dict[str, float] = {
    "topology": 0.25,
    "loading": 0.35,
    "contingency": 0.30,
    "customer": 0.10,
}


def _source_id(nodes: list[dict]) -> str | None:
    return next((n["node_id"] for n in nodes if n.get("node_type") == "substation"), None)


def _build_subtree_sizes(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """Return {edge_id: number_of_nodes_downstream_of_that_edge}.

    BFS from source; node count for an edge is the size of the subtree
    rooted at the edge's to_node (from-node perspective in BFS order).
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
    parent: dict[str, str | None] = {source: None}
    bfs_order: list[str] = []
    queue = [source]
    seen = {source}
    edge_to_child: dict[str, str] = {}
    while queue:
        cur = queue.pop(0)
        bfs_order.append(cur)
        for eid, nbr in sorted(adj.get(cur, [])):
            if nbr not in seen:
                seen.add(nbr)
                parent[nbr] = cur
                edge_to_child[eid] = nbr
                queue.append(nbr)
    subtree: dict[str, int] = {nid: 1 for nid in bfs_order}
    for nid in reversed(bfs_order):
        p = parent.get(nid)
        if p is not None:
            subtree[p] = subtree.get(p, 1) + subtree.get(nid, 1)
    result: dict[str, int] = {}
    for eid, child in edge_to_child.items():
        result[eid] = subtree.get(child, 1)
    return result


def _subtree_nodes_of(
    root: str,
    edge_to_child: dict[str, str],
    adj: dict[str, list[tuple[str, str]]],
    parent: dict[str, str | None],
) -> list[str]:
    result = []
    stack = [root]
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        result.append(cur)
        p = parent.get(cur)
        for _, nbr in adj.get(cur, []):
            if nbr != p and nbr not in seen:
                stack.append(nbr)
    return result


def _normalise_weights(base: dict[str, float], active: set[str]) -> dict[str, float]:
    """Return normalised weights restricted to active dimensions."""
    raw = {k: v for k, v in base.items() if k in active}
    total = sum(raw.values())
    if total <= 0:
        equal = 1.0 / len(raw) if raw else 0.0
        return {k: equal for k in raw}
    return {k: v / total for k, v in raw.items()}


def _build_contingency_severity(ca_result: dict) -> tuple[dict[str, float], float]:
    """Return {edge_id: worst_severity} and max_severity from a CA result."""
    severity: dict[str, float] = {}
    for ct in ca_result.get("contingencies", []):
        eid = ct.get("element")
        sev = ct.get("severity")
        if eid is not None and sev is not None and float(sev) > severity.get(eid, 0.0):
            severity[eid] = float(sev)
    max_sev = max(severity.values(), default=1.0)
    return severity, max_sev if max_sev > 0 else 1.0


def _edge_dim_scores(
    eid: str,
    subtree_sizes: dict[str, int],
    total_nodes: int,
    branch_idx: dict[str, dict],
    cont_severity: dict[str, float],
    max_sev: float,
    customer_counts: dict[str, int],
    total_customers: int,
    active_dims: set[str],
) -> tuple[float, float, float, float]:
    """Return (topo, loading, contingency, customer) dimension scores for one edge."""
    sub = subtree_sizes.get(eid, 1)
    topo = sub / total_nodes if total_nodes > 0 else 0.0
    lp = branch_idx.get(eid, {}).get("loading_pct")
    loading = min(float(lp) / 100.0, 1.0) if lp is not None else 0.0
    cont = cont_severity.get(eid, 0.0) / max_sev if "contingency" in active_dims else 0.0
    n_cust = customer_counts.get(eid, 0)
    customer = (
        n_cust / total_customers if total_customers > 0 and "customer" in active_dims else 0.0
    )
    return topo, loading, cont, customer


def rank_assets(
    nodes: list[dict],
    edges: list[dict],
    pf_result: dict,
    ca_result: dict | None = None,
    customers_by_node: dict[str, int] | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    """Rank distribution network assets by composite criticality score.

    Args:
        nodes: List of node specification dicts.
        edges: List of edge specification dicts.
        pf_result: Power flow result from ``powerflow.solve()``.
        ca_result: Contingency analysis result from ``contingency.analyze()``.
                   When None, the contingency dimension is inactive and its
                   weight is redistributed proportionally to the active dims.
        customers_by_node: Mapping of node_id → customer count. When None,
                           the customer dimension is inactive and its weight
                           is redistributed proportionally to the active dims.
        weights: Optional override for one or more dimension weights. Missing
                 keys fall back to the module-level defaults. Inactive
                 dimension weights are redistributed after merging; see the
                 module docstring for the normalisation formula and examples.

    Returns:
        Dict with keys:
        ``rankings`` (list, sorted by criticality_score descending, ties broken
        by edge_id asc), ``weights_used`` (the final redistributed weights
        actually applied), ``total_assets``, ``most_critical``,
        ``dimensions_active``.
    """
    base_weights = dict(_DEFAULT_WEIGHTS)
    if weights:
        base_weights.update(weights)
    active_dims: set[str] = {"topology", "loading"}
    if ca_result is not None:
        active_dims.add("contingency")
    if customers_by_node is not None:
        active_dims.add("customer")
    w = _normalise_weights(base_weights, active_dims)

    closed_edges = [e for e in edges if e.get("is_closed", True)]
    total_nodes = len(nodes)
    total_customers = sum(customers_by_node.values()) if customers_by_node else 0
    subtree_sizes = _build_subtree_sizes(nodes, edges)
    branch_idx = {b["edge_id"]: b for b in pf_result.get("branches", [])}
    cont_severity, max_sev = (
        _build_contingency_severity(ca_result) if ca_result is not None else ({}, 1.0)
    )
    customer_counts = (
        _build_customer_counts(nodes, edges, customers_by_node) if customers_by_node else {}
    )

    rankings: list[dict] = []
    for e in closed_edges:
        eid = e["edge_id"]
        topo, loading, cont, customer = _edge_dim_scores(
            eid,
            subtree_sizes,
            total_nodes,
            branch_idx,
            cont_severity,
            max_sev,
            customer_counts,
            total_customers,
            active_dims,
        )
        score = (
            w.get("topology", 0.0) * topo
            + w.get("loading", 0.0) * loading
            + w.get("contingency", 0.0) * cont
            + w.get("customer", 0.0) * customer
        )
        rankings.append(
            {
                "edge_id": eid,
                "criticality_score": round(score, 6),
                "topology_score": round(topo, 6),
                "loading_score": round(loading, 6),
                "contingency_score": round(cont, 6),
                "customer_score": round(customer, 6),
                "rank": 0,
            }
        )
    rankings.sort(key=lambda r: (-r["criticality_score"], r["edge_id"]))
    for i, r in enumerate(rankings):
        r["rank"] = i + 1
    most_critical = rankings[0]["edge_id"] if rankings else None
    return {
        "rankings": rankings,
        "weights_used": {k: round(v, 6) for k, v in w.items()},
        "total_assets": len(rankings),
        "most_critical": most_critical,
        "dimensions_active": sorted(active_dims),
    }


def _build_customer_counts(
    nodes: list[dict],
    edges: list[dict],
    customers_by_node: dict[str, int],
) -> dict[str, int]:
    """Return {edge_id: downstream_customer_count} for every closed edge."""
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
    parent: dict[str, str | None] = {source: None}
    bfs_order: list[str] = []
    queue = [source]
    seen = {source}
    edge_to_child: dict[str, str] = {}
    while queue:
        cur = queue.pop(0)
        bfs_order.append(cur)
        for eid, nbr in sorted(adj.get(cur, [])):
            if nbr not in seen:
                seen.add(nbr)
                parent[nbr] = cur
                edge_to_child[eid] = nbr
                queue.append(nbr)
    result: dict[str, int] = {}
    for eid, child in edge_to_child.items():
        subtree = _subtree_nodes_of(child, edge_to_child, adj, parent)
        result[eid] = sum(customers_by_node.get(n, 0) for n in subtree)
    return result
