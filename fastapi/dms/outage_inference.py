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

NOTE (integration, deliberately NOT wired — see follow-ups):
  * This is topologically related to M6 fault_location's last-gasp method, but the
    objective differs: M6 picks the single best-Jaccard section, M7 needs the LCA
    that *covers all* dark meters plus customer estimation. Unifying them is a
    follow-up, not a trivial reuse.
  * M2 state estimation (confirm de-energization from estimated voltage ≈ 0) and M6
    impedance distance (for a true fault vs a planned/lateral outage) would
    corroborate the inference — held as follow-ups.
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


def infer(nodes: list[dict], edges: list[dict], dark_meter_nodes: list[str],
          customers_by_node: dict | None = None, options: dict | None = None) -> dict:
    """Infer probable outage device(s) + affected customers from dark meter nodes."""
    customers_by_node = customers_by_node or {}
    net = build_radial(nodes, edges)
    root, by_id, subtree, parent_edge = net["root"], net["by_id"], net["subtree"], net["parent_edge"]
    parent_node = _parent_node_map(net)
    energized = net["energized"]

    meter_nodes = {n["node_id"] for n in nodes if n["node_type"] == "meter"}
    dark = [d for d in dark_meter_nodes if d in energized]  # only nodes in the model/tree

    def customers_in(node_set) -> int:
        return sum(customers_by_node.get(n, 0) for n in node_set)

    # cluster dark meters by feeding transformer (customer→transformer mapping)
    clusters: dict[str, list[str]] = {}
    for d in dark:
        tx = _nearest_transformer(d, parent_node, root, by_id) or "ROOT"
        clusters.setdefault(tx, []).append(d)

    inferred = []
    for tx, members in clusters.items():
        lca = _lca(members, parent_node, root)
        if lca == root:
            device = None
            section_subtree = set(energized)
        else:
            device_edge = parent_edge[lca]
            attrs = device_edge.get("attrs") or {}
            device = {
                "edge_id": device_edge["edge_id"], "edge_type": device_edge["edge_type"],
                "from": device_edge["from_node"], "to": device_edge["to_node"],
                "device_id": (attrs.get("device_id") if isinstance(attrs, dict) else None),
                "is_switchable": bool(device_edge.get("is_switchable")),
            }
            section_subtree = subtree[device_edge["edge_id"]]
        section_meters = section_subtree & meter_nodes
        est_customers = customers_in(section_subtree)
        reported_customers = customers_in(set(members))
        # confidence: fraction of the section's metered points that went dark
        conf = (len(set(members) & section_meters) / len(section_meters)
                if section_meters else 0.5)
        inferred.append({
            "probable_device": device,
            "section_node": lca,
            "section_name": by_id.get(lca, {}).get("name"),
            "feeding_transformer": (tx if tx != "ROOT" else None),
            "estimated_customers_affected": est_customers,
            "reported_customers": reported_customers,
            "dark_meters": sorted(members),
            "section_meters_total": len(section_meters),
            "confidence": round(conf, 3),
        })

    inferred.sort(key=lambda o: o["estimated_customers_affected"], reverse=True)
    return {
        "method": "AMI last-gasp + topology LCA per feeding transformer; "
                  "affected = all downstream customers (AMI coverage is partial)",
        "dark_meter_count": len(dark),
        "inferred_outages": inferred,
        "outage_count": len(inferred),
    }
