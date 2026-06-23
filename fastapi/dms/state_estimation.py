"""DIEP ADMS P5-M2 — Distribution State Estimation (WLS).

A weighted-least-squares state estimator for radial distribution feeders. Pure
functions over plain dicts — no DB, no framework — so it is unit-testable in
isolation; the DB adapter + endpoint live in routers/dms.py.

Model (linear → single solve, no Gauss-Newton iteration needed)
--------------------------------------------------------------
State x = nodal net injections [p_k (kW), q_k (kvar)] for every energized
non-source node (load positive, generation negative). On a radial feeder the
branch flow into a subtree equals the sum of that subtree's injections, and the
LinDistFlow voltage-drop approximation makes node voltage a *linear* function of
the injections:

    V_n(pu) = 1 - Σ_{b ∈ path(root→n)} [ R_pu(b)·P_b(pu) + X_pu(b)·Q_b(pu) ]
    P_b = Σ_{k ∈ subtree(b)} p_k ,   Q_b = Σ_{k ∈ subtree(b)} q_k

Because both injection measurements and voltage measurements are linear in x, the
WLS estimate is the closed-form normal-equations solution

    x̂ = (Hᵀ W H)⁻¹ Hᵀ W z ,     W = diag(1/σ²)

Measurements z
--------------
  * real injection (telemetry power) — small σ (trusted)
  * voltage magnitude (telemetry voltage, in pu) — small σ
  * pseudo-measurement: every node's base load as its injection — LARGE σ. These
    guarantee observability where telemetry is missing (missing-data handling)
    while contributing almost nothing where real measurements exist.

Diagnostics
-----------
  * bad-data detection: largest-normalized-residual test, rₙ = |r|/√Ω, Ω = R − H G⁻¹ Hᵀ
  * χ² check on the objective J(x̂) = rᵀ W r against dof = m − n
  * per-node confidence from the estimated-voltage variance hₙ G⁻¹ hₙᵀ
"""
from __future__ import annotations

import math

from . import linalg

SBASE_KW = 1000.0  # 1 MVA per-unit base
SQRT3 = math.sqrt(3.0)

# default measurement standard deviations (tunable via options)
DEFAULTS = {
    "sigma_p_meter_kw": 2.0,     # real power telemetry
    "sigma_q_meter_kvar": 2.0,
    "sigma_v_meter_pu": 0.004,   # voltage telemetry (~1 V on LV)
    "sigma_p_pseudo_kw": 30.0,   # nameplate/base-load pseudo-measurement (weak)
    "sigma_q_pseudo_kvar": 20.0,
    "bad_data_threshold": 3.0,   # normalized-residual flag
    "confidence_ref_pu": 0.04,   # voltage std at which confidence → 0
}


def _truthy(v):
    return v is not None


def build_radial(nodes: list[dict], edges: list[dict]) -> dict:
    """Build the energized radial tree from closed edges. Returns root, per-node
    path edges (root→node), per-edge subtree node set, and per-edge pu impedance."""
    by_id = {n["node_id"]: n for n in nodes}
    sources = [n["node_id"] for n in nodes if n["node_type"] == "substation"]
    if not sources:
        raise ValueError("no substation/source node")
    root = sources[0]

    # undirected adjacency over CLOSED edges
    adj: dict[str, list[tuple[str, dict]]] = {n["node_id"]: [] for n in nodes}
    for e in edges:
        if not e.get("is_closed", True):
            continue
        adj[e["from_node"]].append((e["to_node"], e))
        adj[e["to_node"]].append((e["from_node"], e))

    # BFS tree from root: parent edge + ordered path edges per node
    parent_edge: dict[str, dict] = {}
    parent_node: dict[str, str] = {}
    order: list[str] = []
    seen = {root}
    stack = [root]
    while stack:
        cur = stack.pop()
        order.append(cur)
        for nbr, e in adj[cur]:
            if nbr not in seen:
                seen.add(nbr)
                parent_edge[nbr] = e
                parent_node[nbr] = cur
                stack.append(nbr)

    path_edges: dict[str, list[dict]] = {root: []}
    for n in order:
        if n == root:
            continue
        path_edges[n] = path_edges[parent_node[n]] + [parent_edge[n]]

    # subtree(edge) = descendants of its child endpoint (incl. child)
    children: dict[str, list[str]] = {n: [] for n in seen}
    for n in order:
        if n != root:
            children[parent_node[n]].append(n)

    def descendants(start: str) -> set:
        out, st = set(), [start]
        while st:
            c = st.pop()
            out.add(c)
            st.extend(children.get(c, ()))
        return out

    subtree: dict[str, set] = {}
    pu: dict[str, tuple[float, float]] = {}
    for n in order:
        if n == root:
            continue
        e = parent_edge[n]
        subtree[e["edge_id"]] = descendants(n)
        vbase_kv = float(by_id[n].get("nominal_kv") or 0.415)
        zbase = (vbase_kv ** 2) / (SBASE_KW / 1000.0)  # ohms, Sbase in MVA
        r = float(e.get("resistance_r_ohm") or 0.0) / zbase if zbase else 0.0
        x = float(e.get("reactance_x_ohm") or 0.0) / zbase if zbase else 0.0
        pu[e["edge_id"]] = (r, x)

    return {
        "root": root, "by_id": by_id, "energized": seen, "order": order,
        "parent_edge": parent_edge, "path_edges": path_edges,
        "subtree": subtree, "pu": pu,
    }


def estimate(nodes: list[dict], edges: list[dict], measurements: dict,
             options: dict | None = None) -> dict:
    """Run WLS state estimation. `measurements[node_id]` may carry any of
    {p_kw, q_kvar, voltage_pu} (net load convention: consumption positive)."""
    opt = {**DEFAULTS, **(options or {})}
    net = build_radial(nodes, edges)
    root, by_id, energized = net["root"], net["by_id"], net["energized"]
    path_edges, subtree, pu = net["path_edges"], net["subtree"], net["pu"]

    # state vars: p,q per energized non-root node
    state_nodes = [n for n in net["order"] if n != root]
    ip = {nid: 2 * i for i, nid in enumerate(state_nodes)}
    iq = {nid: 2 * i + 1 for i, nid in enumerate(state_nodes)}
    ncol = 2 * len(state_nodes)

    if ncol == 0:
        # nothing energized beyond the source — return a trivial result
        node_results = []
        for n in nodes:
            nid = n["node_id"]
            en = nid in energized
            node_results.append({
                "node_id": nid, "name": n.get("name"), "node_type": n["node_type"],
                "energized": en, "monitored": False,
                "estimated_voltage_pu": (1.0 if nid == root else None),
                "confidence": (1.0 if nid == root else 0.0)})
        return {"method": "WLS (LinDistFlow injection-state, normal equations)",
                "measurements": 0, "states": 0, "redundancy": 0.0, "objective_J": 0.0,
                "dof": 0, "chi2_ok": True, "bad_data": None,
                "max_normalized_residual": 0.0, "nodes": node_results, "branches": []}

    def v_sensitivity_row(node_id: str) -> list[float]:
        """Row of ∂(1−V)/∂x for a (hypothetical or real) voltage at node_id."""
        row = [0.0] * ncol
        for e in path_edges.get(node_id, []):
            r_pu, x_pu = pu[e["edge_id"]]
            for k in subtree[e["edge_id"]]:
                if k in ip:
                    row[ip[k]] += r_pu / SBASE_KW
                    row[iq[k]] += x_pu / SBASE_KW
        return row

    H: list[list[float]] = []
    z: list[float] = []
    w: list[float] = []
    meta: list[dict] = []  # describe each measurement row for residual reporting

    for nid in state_nodes:
        m = measurements.get(nid, {})
        base = by_id[nid]
        # pseudo real injection (always) — anchors observability
        rowp = [0.0] * ncol; rowp[ip[nid]] = 1.0
        H.append(rowp); z.append(float(base.get("base_load_kw") or 0.0))
        w.append(1.0 / opt["sigma_p_pseudo_kw"] ** 2)
        meta.append({"kind": "pseudo_p", "node": nid})
        # pseudo reactive injection
        rowq = [0.0] * ncol; rowq[iq[nid]] = 1.0
        H.append(rowq); z.append(float(base.get("base_load_kvar") or 0.0))
        w.append(1.0 / opt["sigma_q_pseudo_kvar"] ** 2)
        meta.append({"kind": "pseudo_q", "node": nid})
        # real telemetry injection
        if _truthy(m.get("p_kw")):
            rp = [0.0] * ncol; rp[ip[nid]] = 1.0
            H.append(rp); z.append(float(m["p_kw"]))
            w.append(1.0 / opt["sigma_p_meter_kw"] ** 2)
            meta.append({"kind": "meter_p", "node": nid})
        if _truthy(m.get("q_kvar")):
            rq = [0.0] * ncol; rq[iq[nid]] = 1.0
            H.append(rq); z.append(float(m["q_kvar"]))
            w.append(1.0 / opt["sigma_q_meter_kvar"] ** 2)
            meta.append({"kind": "meter_q", "node": nid})
        # voltage telemetry
        if _truthy(m.get("voltage_pu")):
            H.append(v_sensitivity_row(nid))
            z.append(1.0 - float(m["voltage_pu"]))
            w.append(1.0 / opt["sigma_v_meter_pu"] ** 2)
            meta.append({"kind": "meter_v", "node": nid})

    nmeas = len(z)
    # normal equations: G x = Hᵀ W z
    Ht = linalg.transpose(H)
    HtW = [[Ht[i][k] * w[k] for k in range(nmeas)] for i in range(ncol)]
    G = linalg.matmul(HtW, H)
    rhs = linalg.matvec(HtW, z)
    xhat = linalg.solve(G, rhs)
    Ginv = linalg.inverse(G)

    # residuals + bad-data (largest normalized residual)
    pred = linalg.matvec(H, xhat)
    resid = [z[i] - pred[i] for i in range(nmeas)]
    J = sum(w[i] * resid[i] ** 2 for i in range(nmeas))
    dof = max(nmeas - ncol, 1)
    # Ω_ii = R_ii - (H Ginv Hᵀ)_ii
    GinvHt = linalg.matmul(Ginv, Ht)  # ncol x nmeas
    norm_resid = []
    for i in range(nmeas):
        hHt_ii = sum(H[i][c] * GinvHt[c][i] for c in range(ncol))
        omega = (1.0 / w[i]) - hHt_ii
        nr = abs(resid[i]) / math.sqrt(omega) if omega > 1e-12 else 0.0
        norm_resid.append(nr)
    bad = None
    if norm_resid:
        bi = max(range(nmeas), key=lambda i: norm_resid[i])
        if norm_resid[bi] > opt["bad_data_threshold"]:
            bad = {**meta[bi], "normalized_residual": round(norm_resid[bi], 2),
                   "residual": round(resid[bi], 3)}

    # reconstruct flows + voltages from x̂
    def inj(nid, idx):
        return xhat[idx[nid]] if nid in idx else 0.0

    branch = {}
    for nid in state_nodes:
        e = net["parent_edge"][nid]
        eid = e["edge_id"]
        if eid in branch:
            continue
        P = sum(inj(k, ip) for k in subtree[eid])
        Q = sum(inj(k, iq) for k in subtree[eid])
        S = math.hypot(P, Q)
        dnode = by_id[nid]  # child endpoint of this edge
        vll_v = float(dnode.get("nominal_kv") or 0.415) * 1000.0
        amp = e.get("ampacity_a")
        cur = (S * 1000.0) / (SQRT3 * vll_v) if vll_v else 0.0
        if e.get("edge_type") == "transformer" and e.get("rating_kw"):
            loading = 100.0 * S / float(e["rating_kw"])
        elif amp:
            loading = 100.0 * cur / float(amp)
        else:
            loading = None
        branch[eid] = {"edge_id": eid, "from": e["from_node"], "to": e["to_node"],
                       "p_kw": round(P, 2), "q_kvar": round(Q, 2), "s_kva": round(S, 2),
                       "current_a": round(cur, 1),
                       "loading_pct": (round(loading, 1) if loading is not None else None)}

    def voltage_pu(nid):
        v = 1.0
        for e in path_edges.get(nid, []):
            r_pu, x_pu = pu[e["edge_id"]]
            P = sum(inj(k, ip) for k in subtree[e["edge_id"]])
            Q = sum(inj(k, iq) for k in subtree[e["edge_id"]])
            v -= (r_pu * P + x_pu * Q) / SBASE_KW
        return v

    node_results = []
    for n in nodes:
        nid = n["node_id"]
        if nid not in energized:
            node_results.append({"node_id": nid, "name": n.get("name"), "energized": False,
                                 "monitored": False, "estimated_voltage_pu": None,
                                 "confidence": 0.0})
            continue
        monitored = bool(measurements.get(nid))
        if nid == root:
            vpu, conf = 1.0, 1.0
            p_est = q_est = 0.0
        else:
            vpu = voltage_pu(nid)
            hrow = v_sensitivity_row(nid)
            var_v = sum(hrow[a] * Ginv[a][b] * hrow[b]
                        for a in range(ncol) for b in range(ncol))
            std_v = math.sqrt(max(var_v, 0.0))
            conf = max(0.0, min(1.0, 1.0 - std_v / opt["confidence_ref_pu"]))
            if monitored:
                conf = max(conf, 0.85)  # direct measurement floor
            p_est, q_est = inj(nid, ip), inj(nid, iq)
        node_results.append({
            "node_id": nid, "name": n.get("name"), "node_type": n["node_type"],
            "energized": True, "monitored": monitored,
            "estimated_voltage_pu": round(vpu, 4),
            "estimated_voltage_kv": round(vpu * float(n.get("nominal_kv") or 0.0), 4),
            "estimated_p_kw": round(p_est, 2), "estimated_q_kvar": round(q_est, 2),
            "confidence": round(conf, 3),
        })

    return {
        "method": "WLS (LinDistFlow injection-state, normal equations)",
        "measurements": nmeas, "states": ncol, "redundancy": round(nmeas / ncol, 2),
        "objective_J": round(J, 3), "dof": dof,
        "chi2_ok": J <= _chi2_threshold(dof),
        "bad_data": bad,
        "max_normalized_residual": round(max(norm_resid), 2) if norm_resid else 0.0,
        "nodes": node_results,
        "branches": list(branch.values()),
    }


def _chi2_threshold(dof: int) -> float:
    """Upper ~99% χ² critical value, table for small dof with a normal-approx tail."""
    table = {1: 6.63, 2: 9.21, 3: 11.34, 4: 13.28, 5: 15.09, 6: 16.81, 7: 18.48,
             8: 20.09, 9: 21.67, 10: 23.21, 12: 26.22, 15: 30.58, 20: 37.57}
    if dof in table:
        return table[dof]
    # Wilson–Hilferty normal approximation for larger dof
    z = 2.326  # ~99%
    return dof * (1 - 2.0 / (9 * dof) + z * math.sqrt(2.0 / (9 * dof))) ** 3
