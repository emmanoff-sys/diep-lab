"""DIEP ADMS P6-M7 — Outage Detection / Inference.

Infer the *probable failed device* and the *full set of customers affected* from
AMI "last-gasp" / heartbeat-loss signals, the M1 network model, and the
customer-to-transformer mapping. The existing OMS (routers/oms.py) groups dark
meters into a case at the nearest switchable section; M7 sharpens this into a
device-level inference:

  * cluster the dark meters by their feeding transformer (customer→transformer map),
  * for each cluster, find the deepest common ancestor (LCA) of the dark meter nodes
    — the smallest section whose loss explains every dark meter — and attribute the
    outage to the device feeding it,
  * estimate ALL downstream customers (not only those that reported — AMI coverage is
    partial), and score confidence from how cleanly the section's metered customers
    went dark.

Pure functions over plain dicts; reuses the M2/M3 radial tree builder. Read-only.

Two passes (the energized one is primary/authoritative):
  1. ENERGIZED tree (closed edges): the normal case — the outage is not yet reflected
     in topology, so dark meters are still in the energized tree and we localize by
     LCA as above.
  2. STRUCTURAL graph (normally-closed network forced closed; normally-open ties
     excluded): for dark meters that fall OUTSIDE the energized tree because the
     outage is already reflected in topology (a protective device opened). Here the
     probable device is the OPEN protective element on the path, and the section is
     everything structurally downstream of it. This gives an inference node for the
     M2 SE corroboration flags to attach to in exactly that case.
A dark meter is handled by exactly one pass (energized if it is in the energized
tree, else structural), so the structural pass only fills the gap the energized pass
leaves — it never overrides an AMI-energized result.

NOTE (integration, deliberately NOT wired — see follow-ups):
  * This is topologically related to M6 fault_location's last-gasp method, but the
    objective differs: M6 picks the single best-Jaccard section, M7 needs the LCA
    that *covers all* dark meters plus customer estimation. Unifying them is a
    follow-up, not a trivial reuse.
  * M6 impedance distance (for a true fault vs a planned/lateral outage) would further
    refine the inference — held as a follow-up.
"""

from __future__ import annotations

from .state_estimation import build_radial


def _parent_node_map(net: dict) -> dict:
    pn = {}
    for nid, e in net["parent_edge"].items():
        pn[nid] = e["from_node"] if e["to_node"] == nid else e["to_node"]
    return pn


def _ancestors(nid: str, parent_node: dict, root: str) -> list[str]:
    """Path nid → root inclusive (deepest first)."""
    chain, cur, guard = [], nid, 0
    while cur is not None and guard < 1000:
        chain.append(cur)
        if cur == root:
            break
        cur = parent_node.get(cur)
        guard += 1
    return chain


def _lca(dark: list[str], parent_node: dict, root: str) -> str:
    """Deepest common ancestor of the dark nodes."""
    if not dark:
        return root
    common = None
    for d in dark:
        anc = _ancestors(d, parent_node, root)
        s = set(anc)
        common = s if common is None else (common & s)
    # pick the deepest node in the intersection (longest path to root)
    depth = {n: len(_ancestors(n, parent_node, root)) for n in common}
    return max(common, key=lambda n: depth[n])


def _nearest_transformer(nid: str, parent_node: dict, root: str, by_id: dict) -> str | None:
    for n in _ancestors(nid, parent_node, root):
        if by_id.get(n, {}).get("node_type") == "transformer":
            return n
    return None


def _isolating_open_edge(
    lca: str, parent_edge: dict, parent_node: dict, root: str, open_edge_ids: set
) -> dict | None:
    """Walk the structural path lca → root; return the first OPEN protective edge
    (the device whose opening de-energized this section)."""
    cur = lca
    while cur is not None and cur != root:
        e = parent_edge.get(cur)
        if e is None:
            break
        if e["edge_id"] in open_edge_ids:
            return e
        cur = parent_node.get(cur)
    return None


def _infer_pass(
    dark: list[str],
    net: dict,
    meter_nodes: set,
    customers_in,
    se_dead: set,
    source: str,
    open_edge_ids: set | None,
) -> list[dict]:
    """One inference pass over a tree (`net` from build_radial). For the structural
    pass, `open_edge_ids` lets the probable device be the open protective element."""
    if not dark:
        return []
    root, by_id = net["root"], net["by_id"]
    parent_edge, subtree = net["parent_edge"], net["subtree"]
    parent_node = _parent_node_map(net)

    clusters: dict[str, list[str]] = {}
    for d in dark:
        tx = _nearest_transformer(d, parent_node, root, by_id) or "ROOT"
        clusters.setdefault(tx, []).append(d)

    out = []
    for tx, members in clusters.items():
        lca = _lca(members, parent_node, root)
        device_edge = None
        if source == "structural" and open_edge_ids:
            device_edge = _isolating_open_edge(lca, parent_edge, parent_node, root, open_edge_ids)
        if device_edge is None and lca != root:
            device_edge = parent_edge[lca]

        if device_edge is not None:
            attrs = device_edge.get("attrs") or {}
            device = {
                "edge_id": device_edge["edge_id"],
                "edge_type": device_edge["edge_type"],
                "from": device_edge["from_node"],
                "to": device_edge["to_node"],
                "device_id": (attrs.get("device_id") if isinstance(attrs, dict) else None),
                "is_switchable": bool(device_edge.get("is_switchable")),
            }
            section_subtree = subtree[device_edge["edge_id"]]
            section_node = device_edge["to_node"]
        else:  # whole-feeder (lca == root)
            device = None
            section_subtree = set(net["energized"])
            section_node = root

        section_meters = section_subtree & meter_nodes
        conf = len(set(members) & section_meters) / len(section_meters) if section_meters else 0.5
        out.append(
            {
                "probable_device": device,
                "section_node": section_node,
                "section_name": by_id.get(section_node, {}).get("name"),
                "feeding_transformer": (tx if tx != "ROOT" else None),
                "estimated_customers_affected": customers_in(section_subtree),
                "reported_customers": customers_in(set(members)),
                "dark_meters": sorted(members),
                "section_meters_total": len(section_meters),
                "confidence": round(conf, 3),
                "source": source,
                "corroborated_by_se": bool(set(members) & se_dead),
            }
        )
    return out


def infer(
    nodes: list[dict],
    edges: list[dict],
    dark_meter_nodes: list[str],
    customers_by_node: dict | None = None,
    options: dict | None = None,
    se_dead_nodes: list[str] | None = None,
) -> dict:
    """Infer probable outage device(s) + affected customers from dark meter nodes.

    Runs the energized-tree pass first (primary/authoritative). Dark meters that fall
    outside the energized tree — because the outage is already reflected in topology
    (a protective device opened) — are localized by a second STRUCTURAL pass, so the
    M2 SE corroboration flags have an inference node to attach to even then.

    `se_dead_nodes` (optional, from M2 state estimation): nodes the estimator reads as
    de-energized / dead-voltage. Used ONLY as a secondary corroboration signal — it
    never changes the AMI-based inference. Sets `corroborated_by_se` per inferred
    outage and surfaces *silent failures* — meters SE reads dead that did NOT report a
    last-gasp."""
    customers_by_node = customers_by_node or {}
    se_dead = set(se_dead_nodes or [])
    meter_nodes = {n["node_id"] for n in nodes if n["node_type"] == "meter"}

    def customers_in(node_set) -> int:
        return sum(customers_by_node.get(n, 0) for n in node_set)

    # primary: energized tree (closed edges)
    enet = build_radial(nodes, edges)
    energized = enet["energized"]

    # secondary: structural graph — normally-closed network forced closed (a tripped
    # protective device is still 'present'), normally-open ties excluded.
    structural_edges = [{**e, "is_closed": True} for e in edges if e.get("normally_closed", True)]
    snet = build_radial(nodes, structural_edges)
    s_energized = snet["energized"]
    open_edge_ids = {
        e["edge_id"]
        for e in edges
        if not e.get("is_closed", True) and e.get("normally_closed", True)
    }

    dark_primary = [d for d in dark_meter_nodes if d in energized]
    dark_fallback = [d for d in dark_meter_nodes if d not in energized and d in s_energized]

    inferred = _infer_pass(
        dark_primary, enet, meter_nodes, customers_in, se_dead, "energized", None
    ) + _infer_pass(
        dark_fallback, snet, meter_nodes, customers_in, se_dead, "structural", open_edge_ids
    )
    inferred.sort(key=lambda o: o["estimated_customers_affected"], reverse=True)

    dark_located = set(dark_primary) | set(dark_fallback)
    silent_nodes = sorted((se_dead & meter_nodes) - dark_located)
    return {
        "method": "AMI last-gasp + topology LCA per feeding transformer; energized "
        "tree primary, structural graph fallback for topology-reflected "
        "outages; affected = all downstream customers (AMI coverage is partial)",
        "dark_meter_count": len(dark_located),
        "inferred_outages": inferred,
        "outage_count": len(inferred),
        "silent_failure_suspected": bool(silent_nodes),
        "silent_failure_nodes": silent_nodes,
    }
