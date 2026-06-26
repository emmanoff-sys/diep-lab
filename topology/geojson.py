"""GeoJSON -> DIEP grid_nodes/grid_edges mapping. Pure parsing, no DB/network
access — matches the fastapi/dms/ convention of pure functions over plain
dicts, so this is unit-testable without the live stack (see
tests/test_topology_importer.py).

Source shape observed in NREL/DOE SMART-DS exports (see
tests/fixtures/SOURCE.md for provenance): a FeatureCollection of

  * Point features, properties.type in {"Node", "Transformer", "Load"};
  * LineString features, properties.type == "Line", with is_switch/is_open
    booleans, "length (km)", ampacity, phases.

Connectivity is NOT given by an explicit from/to property — it is implied by
exact coordinate coincidence between a LineString's endpoints and "Node"
Point features. "Transformer" and "Load" points share a coordinate with the
"Node" point they attach to (a transformer's primary/secondary bushing, a
customer's service point) rather than being separate graph vertices, so they
are folded into the schema's existing conventions instead of becoming new
nodes:
  * a Transformer point becomes a `transformer`-typed EDGE directly between
    the two Node points named in its own "tr(r:<primary>-<secondary>)" id —
    mirrors DIEP's own modeling note that a transformer is the *edge*
    spanning two voltage levels, not a separate busbar (see
    P5_M1_NETWORK_MODEL_DESIGN.md "Impedance referencing convention").
  * a Load point's max_kw/max_kvar are accumulated onto the base_load_kw/
    base_load_kvar of the Node point at its coordinate — same convention the
    Abuja Site A seed uses (load is a node attribute, not a node).
This keeps "Node" points as the only graph vertices, so coordinate matching
is unambiguous (no two Node points in the observed fixture share a
coordinate) without needing name-based disambiguation.
"""
from __future__ import annotations

import re

NODE_TYPE_MAP = {"Node": "bus"}  # Transformer/Load are folded, not mapped 1:1
_TR_NAME_RE = re.compile(r"^tr\(r:(.+)\)$")
_LINE_NAME_RE = re.compile(r"^l\(r:(.+?)\)(?:_\w+)?$")
_COORD_PRECISION = 6


def _round_coord(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, _COORD_PRECISION), round(lat, _COORD_PRECISION))


def _phases(raw) -> str:
    """['A','B','C'] -> 'ABC'; ['CT'] (center-tap secondary, no ABC concept
    in DIEP's schema) -> single-phase 'A', raw code preserved in attrs."""
    if not raw:
        return "ABC"
    letters = "".join(p for p in raw if p in ("A", "B", "C"))
    return letters or "A"


def _split_pair(text: str, known_ids: set[str]) -> tuple[str, str] | None:
    """Split 'A-B' into (A, B) when both halves are known node ids — handles
    ids that themselves contain hyphens by trying every split point rather
    than assuming the first/last hyphen is the separator."""
    for i, ch in enumerate(text):
        if ch != "-":
            continue
        a, b = text[:i], text[i + 1:]
        if a in known_ids and b in known_ids:
            return a, b
    return None


def parse_feature_collection(fc: dict) -> dict:
    """Returns {"nodes": [...], "edges": [...], "unresolved": [...]}.

    nodes: node_id, node_type, name, latitude, longitude, base_load_kw,
           base_load_kvar, attrs (plain dicts, shaped for topology.loader).
    edges: edge_id, from_node, to_node, edge_type, is_switchable,
           normally_closed, is_closed, length_km, ampacity_a, phases, attrs.
    unresolved: LineString/Transformer features whose endpoints couldn't be
           matched to a known node — surfaced, never silently dropped.
    """
    features = fc.get("features", [])
    point_feats = [f for f in features if (f.get("geometry") or {}).get("type") == "Point"]
    line_feats = [f for f in features if (f.get("geometry") or {}).get("type") == "LineString"]

    nodes: list[dict] = []
    by_id: dict[str, dict] = {}
    coord_index: dict[tuple[float, float], str] = {}
    load_feats, transformer_feats = [], []

    for f in point_feats:
        props = f.get("properties") or {}
        src_type = props.get("type", "Node")
        if src_type == "Load":
            load_feats.append(f)
            continue
        if src_type == "Transformer":
            transformer_feats.append(f)
            continue
        node_id = str(props.get("name") or "").strip()
        if not node_id or node_id in by_id:
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        node = {
            "node_id": node_id, "node_type": NODE_TYPE_MAP.get(src_type, "bus"),
            "name": node_id, "latitude": lat, "longitude": lon,
            "base_load_kw": 0.0, "base_load_kvar": 0.0,
            "attrs": {"source": "smart-ds", "source_type": src_type},
        }
        nodes.append(node)
        by_id[node_id] = node
        coord_index[_round_coord(lon, lat)] = node_id

    unresolved: list[dict] = []

    # Loads: accumulate onto the Node at the same coordinate (no separate vertex).
    for f in load_feats:
        props = f.get("properties") or {}
        lon, lat = f["geometry"]["coordinates"][:2]
        target_id = coord_index.get(_round_coord(lon, lat))
        if target_id is None:
            unresolved.append({"kind": "load", "name": props.get("name"),
                                "reason": "no Node at this coordinate"})
            continue
        node = by_id[target_id]
        node["base_load_kw"] += float(props.get("max_kw") or 0)
        node["base_load_kvar"] += float(props.get("max_kvar") or 0)
        node["attrs"].setdefault("loads", []).append({
            "name": props.get("name"), "rated_kv": props.get("rated_kv"),
            "is_ct": bool(props.get("is_ct")),
        })

    edges: list[dict] = []

    # Transformers: become a transformer-typed edge between the two Node ids
    # named in "tr(r:<primary>-<secondary>)" — see module docstring.
    for f in transformer_feats:
        props = f.get("properties") or {}
        raw_name = props.get("name") or ""
        m = _TR_NAME_RE.match(raw_name)
        pair = _split_pair(m.group(1), set(by_id)) if m else None
        if pair is None:
            unresolved.append({"kind": "transformer", "name": raw_name,
                                "reason": "could not resolve primary/secondary node ids"})
            continue
        from_id, to_id = pair
        edges.append({
            "edge_id": raw_name, "from_node": from_id, "to_node": to_id,
            "edge_type": "transformer", "is_switchable": False,
            "normally_closed": True, "is_closed": True,
            "length_km": 0.0, "ampacity_a": None, "phases": "ABC",
            "attrs": {"source": "smart-ds", "source_name": raw_name,
                      "kva": props.get("kva"), "kvs": props.get("kvs")},
        })
        kvs = props.get("kvs") or []
        if len(kvs) >= 2:
            try:
                by_id[from_id]["nominal_kv"] = float(kvs[0])
                by_id[to_id]["nominal_kv"] = float(kvs[1])
            except (TypeError, ValueError):
                pass

    # Lines: resolve endpoints by exact coordinate match against Node points.
    for f in line_feats:
        props = f.get("properties") or {}
        raw_name = props.get("name") or ""
        coords = f["geometry"]["coordinates"]
        start_id = coord_index.get(_round_coord(*coords[0][:2]))
        end_id = coord_index.get(_round_coord(*coords[-1][:2]))
        if start_id is None or end_id is None:
            unresolved.append({"kind": "line", "name": raw_name,
                                "reason": f"endpoint unresolved (start={start_id}, end={end_id})"})
            continue
        is_switch = bool(props.get("is_switch"))
        is_open = bool(props.get("is_open"))
        edges.append({
            "edge_id": raw_name or f"edge-{len(edges)}",
            "from_node": start_id, "to_node": end_id,
            "edge_type": "switch" if is_switch else "line",
            "is_switchable": is_switch,
            "normally_closed": not is_open, "is_closed": not is_open,
            "length_km": float(props.get("length (km)") or 0),
            "ampacity_a": float(props.get("ampacity") or 0) or None,
            "phases": _phases(props.get("phases")),
            "attrs": {"source": "smart-ds", "source_name": raw_name,
                      "is_fuse": bool(props.get("is_fuse")),
                      "is_ct": bool(props.get("is_ct"))},
        })

    _propagate_nominal_kv(by_id, edges)
    return {"nodes": nodes, "edges": edges, "unresolved": unresolved}


def _propagate_nominal_kv(by_id: dict[str, dict], edges: list[dict]) -> None:
    """Transformer edges fix nominal_kv at the two voltage levels they
    bridge; 'line'/'switch' edges don't change voltage, so carry a known
    nominal_kv across them to the other endpoint until nothing changes."""
    changed = True
    while changed:
        changed = False
        for e in edges:
            if e["edge_type"] == "transformer":
                continue
            a, b = by_id[e["from_node"]], by_id[e["to_node"]]
            if a.get("nominal_kv") is not None and b.get("nominal_kv") is None:
                b["nominal_kv"] = a["nominal_kv"]
                changed = True
            elif b.get("nominal_kv") is not None and a.get("nominal_kv") is None:
                a["nominal_kv"] = b["nominal_kv"]
                changed = True


def orient_radial(nodes: list[dict], edges: list[dict], root_id: str) -> dict:
    """DFS from `root_id` over the undirected edge set to pick a direction for
    every edge (parent->child, the direction common.downstream_node_ids() and
    the OMS/FLISR walk follow) and to set each non-root node's parent_id. The
    source GeoJSON has no upstream/downstream concept (edge direction is just
    LineString start/end order), so the caller must say which imported node is
    the upstream connection point — there is no reliable way to infer it from
    the file alone.

    Edges that close a loop (both endpoints already reached, e.g. a tie) are
    kept — oriented by discovery order — rather than dropped; only the n-1
    spanning-tree edges set parent_id, matching how DIEP's own tie switch
    (E-TIE-01) is connectivity without being part of the hierarchy.
    """
    by_id = {n["node_id"]: n for n in nodes}
    if root_id not in by_id:
        raise ValueError(f"root_id '{root_id}' not among parsed nodes")

    adj: dict[str, list[str]] = {nid: [] for nid in by_id}
    for e in edges:
        adj[e["from_node"]].append(e["to_node"])
        adj[e["to_node"]].append(e["from_node"])

    discovery = {root_id: 0}
    order = [root_id]
    stack = [root_id]
    while stack:
        cur = stack.pop()
        for nxt in adj[cur]:
            if nxt not in discovery:
                discovery[nxt] = len(order)
                order.append(nxt)
                by_id[nxt]["parent_id"] = cur
                stack.append(nxt)

    unreached = sorted(set(by_id) - set(discovery))
    oriented = []
    for e in edges:
        a, b = e["from_node"], e["to_node"]
        if a not in discovery or b not in discovery:
            oriented.append(dict(e))  # disconnected component — leave as-is
            continue
        upstream, downstream = (a, b) if discovery[a] <= discovery[b] else (b, a)
        oriented.append({**e, "from_node": upstream, "to_node": downstream})

    return {"nodes": nodes, "edges": oriented, "unreached": unreached}
