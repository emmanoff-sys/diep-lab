"""DIEP ADMS P5-M3 — Unbalanced (three-phase) Power Flow.

A three-phase backward/forward sweep (ladder-iterative) power-flow solver for
radial distribution feeders. Pure functions over plain dicts + Python's built-in
`complex` — no numpy, no DB, no framework. The DB adapter + endpoint live in
routers/dms.py.

Method
------
Radial feeders converge reliably with the current-summation backward/forward
sweep (Berg/Kersting), which avoids forming/inverting an admittance matrix:

  init   : flat start — every node phase at the slack profile (1∠0/−120/+120 pu)
  repeat :
    backward : nodal load currents  iₙ = conj(Sₙ / Vₙ);  branch current Jb = Σ
               (subtree load currents)                          [leaves → root]
    forward  : Vchild = Vparent − Zb·Jb                          [root → leaves]
  until    max |ΔV| < tol  (or max iterations)

Unbalance is real: per-phase loads, single-phase laterals (M1 `phases`), and DER
injection (negative load) produce genuinely different phase voltages. Series
impedance is per-phase scalar (no mutual coupling) — a deliberate first model;
the modular Branch/Solver split lets a full Carson 3×3 Zabcc replace it later
without touching the sweep driver. Likewise transformers are modeled as series
impedance (ratio handled by each node's own kV base); delta-wye phase shift is a
documented future extension.
"""
from __future__ import annotations

import cmath
import math

from .state_estimation import build_radial, SBASE_KW

# Per-phase power base = (three-phase 1 MVA) / 3. With line-to-line voltage bases
# (nominal_kv) and Zbase = V_LL²/S_3ph, the per-phase pu current conj(S_1φ/V) then
# equals the line current in pu, and the per-phase voltage drop z_pu·I_pu matches
# the three-phase single-line result. (Line/phase current base is identical:
# I_base = S_3ph/(√3·V_LL).)
SBASE_1PH_KW = SBASE_KW / 3.0

PHASES = ("a", "b", "c")
# balanced positive-sequence slack reference (per-unit)
SLACK = {"a": cmath.rect(1.0, 0.0),
         "b": cmath.rect(1.0, math.radians(-120.0)),
         "c": cmath.rect(1.0, math.radians(120.0))}

DEFAULTS = {"tol_pu": 1e-6, "max_iter": 100, "v_min_pu": 0.95, "v_max_pu": 1.05}


def _phase_set(s: str | None) -> list[str]:
    s = (s or "ABC").lower()
    return [p for p in PHASES if p in s]


def solve(nodes: list[dict], edges: list[dict], loads: dict,
          options: dict | None = None) -> dict:
    """Solve three-phase power flow.

    `loads[node_id][phase]` = complex(P_kw, Q_kvar), net load (consumption +,
    generation/DER −). Phases not present on a node are omitted.
    """
    opt = {**DEFAULTS, **(options or {})}
    net = build_radial(nodes, edges)
    root, by_id, energized = net["root"], net["by_id"], net["energized"]
    parent_edge, path_edges, subtree, pu = (net["parent_edge"], net["path_edges"],
                                            net["subtree"], net["pu"])
    order = net["order"]  # BFS order from root (parents before children)

    node_phases = {n["node_id"]: _phase_set(n.get("phases")) for n in nodes}
    edge_phases = {e["edge_id"]: set(_phase_set(e.get("phases"))) for e in edges}
    z_pu = {eid: complex(r, x) for eid, (r, x) in pu.items()}

    # per-edge child node + the phases it actually carries
    child_of = {parent_edge[n]["edge_id"]: n for n in order if n != root}
    branch_phase = {eid: [p for p in node_phases[child_of[eid]] if p in edge_phases[eid]]
                    for eid in child_of}

    # voltages: dict[node][phase] = complex pu. flat start at slack.
    V = {nid: {p: SLACK[p] for p in node_phases[nid]} for nid in energized}

    converged, iters, max_mismatch = False, 0, 0.0
    for it in range(1, opt["max_iter"] + 1):
        iters = it
        # --- backward: nodal load currents, then branch currents -------------
        i_load = {nid: {} for nid in energized}
        for nid in energized:
            ld = loads.get(nid, {})
            for p in node_phases[nid]:
                s = ld.get(p)
                if s is None:
                    i_load[nid][p] = 0j
                    continue
                s_pu = complex(s.real, s.imag) / SBASE_1PH_KW
                vp = V[nid].get(p) or SLACK[p]
                i_load[nid][p] = (s_pu / vp).conjugate()
        # branch current = sum of subtree load currents:  Jb = Σ_{k∈subtree} i_load[k]
        J = {}
        for eid in child_of:
            tot = {p: 0j for p in branch_phase[eid]}
            for k in subtree[eid]:
                for p in branch_phase[eid]:
                    tot[p] += i_load.get(k, {}).get(p, 0j)
            J[eid] = tot

        # --- forward: update voltages ----------------------------------------
        mismatch = 0.0
        for nid in order:
            if nid == root:
                continue
            e = parent_edge[nid]
            eid = e["edge_id"]
            parent = e["from_node"] if e["to_node"] == nid else e["to_node"]
            z = z_pu[eid]
            for p in node_phases[nid]:
                vparent = V[parent].get(p, SLACK[p])
                jb = J[eid].get(p, 0j) if p in branch_phase[eid] else 0j
                vnew = vparent - z * jb
                mismatch = max(mismatch, abs(vnew - V[nid][p]))
                V[nid][p] = vnew
        max_mismatch = mismatch
        if mismatch < opt["tol_pu"]:
            converged = True
            break

    # --- assemble results ----------------------------------------------------
    node_results, violations = [], []
    for n in nodes:
        nid = n["node_id"]
        if nid not in energized:
            node_results.append({"node_id": nid, "name": n.get("name"),
                                 "energized": False, "phases": {}})
            continue
        kv = float(n.get("nominal_kv") or 0.415)
        vbase_ln = kv * 1000.0 / math.sqrt(3.0)  # phase (line-neutral) base volts
        phase_v = {}
        mags = []
        for p in node_phases[nid]:
            vp = V[nid][p]
            mag = abs(vp)
            mags.append(mag)
            phase_v[p] = {"v_pu": round(mag, 4), "v_volts": round(mag * vbase_ln, 1),
                          "angle_deg": round(math.degrees(cmath.phase(vp)), 2)}
            if mag < opt["v_min_pu"] or mag > opt["v_max_pu"]:
                violations.append({"type": "voltage", "node": nid, "phase": p,
                                   "v_pu": round(mag, 4)})
        vmin = min(mags) if mags else None
        vavg = sum(mags) / len(mags) if mags else None
        # voltage unbalance factor (%), meaningful for 3-phase nodes
        vuf = (round(100.0 * max(abs(m - vavg) for m in mags) / vavg, 2)
               if vavg and len(mags) == 3 else None)
        node_results.append({
            "node_id": nid, "name": n.get("name"), "node_type": n["node_type"],
            "energized": True, "phases": phase_v,
            "v_min_pu": (round(vmin, 4) if vmin is not None else None),
            "v_avg_pu": (round(vavg, 4) if vavg is not None else None),
            "unbalance_pct": vuf})

    branch_results = []
    total_loss_kw = 0.0
    for n in order:
        if n == root:
            continue
        e = parent_edge[n]
        eid = e["edge_id"]
        c = child_of[eid]
        kv = float(by_id[c].get("nominal_kv") or 0.415)
        vll = kv * 1000.0
        r_ohm = float(e.get("resistance_r_ohm") or 0.0)
        per_phase = {}
        s_total = 0.0
        max_i = 0.0
        loss_kw = 0.0
        for p in branch_phase[eid]:
            jb = J[eid].get(p, 0j)
            i_a = abs(jb) * SBASE_KW / (math.sqrt(3.0) * kv)  # pu I → line amps
            max_i = max(max_i, i_a)
            # per-phase apparent power S = V·I* (pu) → kVA (per-phase base)
            vp = V[c].get(p, SLACK[p])
            s_kva = abs(vp * jb.conjugate()) * SBASE_1PH_KW
            s_total += s_kva
            loss_kw += (i_a ** 2) * r_ohm / 1000.0  # I²R per phase
            per_phase[p] = {"current_a": round(i_a, 1), "s_kva": round(s_kva, 2)}
        total_loss_kw += loss_kw
        amp = e.get("ampacity_a")
        if e.get("edge_type") == "transformer" and e.get("rating_kw"):
            loading = round(100.0 * s_total / float(e["rating_kw"]), 1)
            basis = "rating_kva"
        elif amp:
            loading = round(100.0 * max_i / float(amp), 1)
            basis = "ampacity"
        else:
            loading, basis = None, None
        if loading is not None and loading > 100.0:
            violations.append({"type": "thermal", "edge": eid, "loading_pct": loading})
        branch_results.append({
            "edge_id": eid, "from": e["from_node"], "to": e["to_node"],
            "edge_type": e["edge_type"], "phases": per_phase,
            "s_kva": round(s_total, 2), "loss_kw": round(loss_kw, 3),
            "loading_pct": loading, "loading_basis": basis})

    return {
        "method": "three-phase backward/forward sweep (radial, per-phase series Z)",
        "converged": converged, "iterations": iters,
        "max_mismatch_pu": round(max_mismatch, 9),
        "total_loss_kw": round(total_loss_kw, 3),
        "tolerance_pu": opt["tol_pu"],
        "v_band_pu": [opt["v_min_pu"], opt["v_max_pu"]],
        "violations": violations,
        "violation_count": len(violations),
        "nodes": node_results, "branches": branch_results,
    }
