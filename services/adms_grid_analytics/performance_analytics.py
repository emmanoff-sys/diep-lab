"""DIEP ADMS P5-M11 — Operational Performance Analytics (OA-134).

Aggregated quality metrics derived from power flow, contingency, and VVO
results. No independent computation is performed — values are read from
the existing result structures.

Voltage band
------------
Default band: 0.95 pu ≤ V ≤ 1.05 pu (±5 %).  Only energised nodes with
a non-None v_avg_pu contribute to voltage quality statistics.

Loading distribution buckets
-----------------------------
  light      0 %  ≤ loading <  50 %
  moderate  50 %  ≤ loading <  80 %
  heavy     80 %  ≤ loading < 100 %
  overloaded     loading ≥ 100 %

Overall health
--------------
  red    violation_count > 0  OR  overloaded branches > 0  OR  ca_result
         present and n1_secure is False
  amber  any branch in the heavy bucket (80–100 %)
  green  otherwise
"""

from __future__ import annotations

import math

_V_LOW = 0.95
_V_HIGH = 1.05


def voltage_profile_quality(pf_result: dict) -> dict:
    """Return voltage quality metrics across all energised nodes.

    Returns:
        Dict with keys:
        ``energised_nodes``, ``mean_v_pu``, ``std_v_pu``,
        ``min_v_pu``, ``max_v_pu``,
        ``nodes_in_band``, ``nodes_out_of_band``,
        ``band_compliance_pct``, ``max_unbalance_pct``.
    """
    voltages: list[float] = []
    unbalances: list[float] = []
    for n in pf_result.get("nodes", []):
        if not n.get("energized", True):
            continue
        v = n.get("v_avg_pu")
        if v is not None:
            voltages.append(float(v))
        u = n.get("unbalance_pct")
        if u is not None:
            unbalances.append(float(u))
    if not voltages:
        return {
            "energised_nodes": 0,
            "mean_v_pu": None,
            "std_v_pu": None,
            "min_v_pu": None,
            "max_v_pu": None,
            "nodes_in_band": 0,
            "nodes_out_of_band": 0,
            "band_compliance_pct": None,
            "max_unbalance_pct": None,
        }
    mean_v = sum(voltages) / len(voltages)
    variance = sum((v - mean_v) ** 2 for v in voltages) / len(voltages)
    std_v = math.sqrt(variance)
    in_band = sum(1 for v in voltages if _V_LOW <= v <= _V_HIGH)
    out_band = len(voltages) - in_band
    return {
        "energised_nodes": len(voltages),
        "mean_v_pu": round(mean_v, 6),
        "std_v_pu": round(std_v, 6),
        "min_v_pu": round(min(voltages), 6),
        "max_v_pu": round(max(voltages), 6),
        "nodes_in_band": in_band,
        "nodes_out_of_band": out_band,
        "band_compliance_pct": round(100.0 * in_band / len(voltages), 1),
        "max_unbalance_pct": round(max(unbalances), 3) if unbalances else None,
    }


def loading_distribution(pf_result: dict) -> dict:
    """Return loading distribution across all branches.

    Only rated branches (loading_pct not None) contribute to buckets
    and statistics.

    Returns:
        Dict with keys:
        ``rated_branches``, ``unrated_branches``,
        ``buckets`` (dict with ``light``, ``moderate``, ``heavy``,
        ``overloaded`` counts),
        ``mean_loading_pct``, ``max_loading_pct``, ``min_loading_pct``,
        ``overloaded_count``.
    """
    branches = pf_result.get("branches", [])
    rated = [b for b in branches if b.get("loading_pct") is not None]
    unrated = len(branches) - len(rated)
    buckets = {"light": 0, "moderate": 0, "heavy": 0, "overloaded": 0}
    loading_vals: list[float] = []
    for b in rated:
        lp = float(b["loading_pct"])
        loading_vals.append(lp)
        if lp >= 100.0:
            buckets["overloaded"] += 1
        elif lp >= 80.0:
            buckets["heavy"] += 1
        elif lp >= 50.0:
            buckets["moderate"] += 1
        else:
            buckets["light"] += 1
    mean_lp = sum(loading_vals) / len(loading_vals) if loading_vals else None
    return {
        "rated_branches": len(rated),
        "unrated_branches": unrated,
        "buckets": buckets,
        "mean_loading_pct": round(mean_lp, 1) if mean_lp is not None else None,
        "max_loading_pct": round(max(loading_vals), 1) if loading_vals else None,
        "min_loading_pct": round(min(loading_vals), 1) if loading_vals else None,
        "overloaded_count": buckets["overloaded"],
    }


def contingency_exposure(ca_result: dict) -> dict:
    """Return contingency exposure metrics.

    When ca_result is None-like (empty dict), returns safe defaults.

    Returns:
        Dict with keys:
        ``n1_secure``, ``contingencies_evaluated``, ``critical_count``,
        ``major_count``, ``minor_count``, ``worst_element``,
        ``max_unserved_kw``, ``total_unserved_kw``.
    """
    if not ca_result:
        return {
            "n1_secure": None,
            "contingencies_evaluated": 0,
            "critical_count": 0,
            "major_count": 0,
            "minor_count": 0,
            "worst_element": None,
            "max_unserved_kw": 0.0,
            "total_unserved_kw": 0.0,
        }
    summary = ca_result.get("impact_summary", {}) or {}
    contingencies = ca_result.get("contingencies", [])
    worst = ca_result.get("worst", [])
    worst_element = worst[0].get("element") if worst else None
    total_unserved = sum(float(c.get("unserved_load_kw") or 0.0) for c in contingencies)
    max_unserved = max(
        (float(c.get("unserved_load_kw") or 0.0) for c in contingencies), default=0.0
    )
    return {
        "n1_secure": ca_result.get("n1_secure"),
        "contingencies_evaluated": ca_result.get("contingencies_evaluated", len(contingencies)),
        "critical_count": summary.get("critical_count", 0),
        "major_count": summary.get("major_count", 0),
        "minor_count": summary.get("minor_count", 0),
        "worst_element": worst_element,
        "max_unserved_kw": round(max_unserved, 2),
        "total_unserved_kw": round(total_unserved, 2),
    }


def optimisation_benefit(vvo_result: dict) -> dict:
    """Return VVO optimisation benefit metrics.

    Returns:
        Dict with keys:
        ``devices_evaluated``, ``configurations_evaluated``,
        ``base_violations``, ``optimal_violations``, ``violation_reduction``,
        ``base_loss_kw``, ``optimal_loss_kw``, ``loss_reduction_kw``,
        ``optimal_score``, ``optimisation_effective``.
    """
    if not vvo_result:
        return {
            "devices_evaluated": 0,
            "configurations_evaluated": 0,
            "base_violations": 0,
            "optimal_violations": 0,
            "violation_reduction": 0,
            "base_loss_kw": 0.0,
            "optimal_loss_kw": 0.0,
            "loss_reduction_kw": 0.0,
            "optimal_score": None,
            "optimisation_effective": False,
        }
    base = vvo_result.get("base_case", {}) or {}
    opt = vvo_result.get("optimal_case", {}) or {}
    configs = vvo_result.get("configurations", [])
    devices = len(vvo_result.get("optimal_state", {}) or {})
    base_v = int(base.get("violation_count") or 0)
    opt_v = int(opt.get("violation_count") or 0)
    base_l = float(base.get("total_loss_kw") or 0.0)
    opt_l = float(opt.get("total_loss_kw") or 0.0)
    return {
        "devices_evaluated": devices,
        "configurations_evaluated": len(configs),
        "base_violations": base_v,
        "optimal_violations": opt_v,
        "violation_reduction": base_v - opt_v,
        "base_loss_kw": round(base_l, 3),
        "optimal_loss_kw": round(opt_l, 3),
        "loss_reduction_kw": round(base_l - opt_l, 3),
        "optimal_score": vvo_result.get("optimal_score"),
        "optimisation_effective": (opt_v < base_v) or (opt_l < base_l),
    }


def operational_performance(
    nodes: list[dict],
    edges: list[dict],
    pf_result: dict,
    ca_result: dict | None = None,
    vvo_result: dict | None = None,
) -> dict:
    """Produce an integrated operational performance report.

    Returns:
        Dict with keys:
        ``voltage_quality``, ``loading``, ``contingency_exposure``,
        ``optimisation_benefit``, ``overall_health``.

    Overall health:
        ``red``   — thermal violations or n-1 insecure
        ``amber`` — heavy loading (80–100 %) present
        ``green`` — no identified issues
    """
    vq = voltage_profile_quality(pf_result)
    ld = loading_distribution(pf_result)
    ce = contingency_exposure(ca_result or {})
    ob = optimisation_benefit(vvo_result or {})
    violation_count = int(pf_result.get("violation_count") or 0)
    overloaded = ld["overloaded_count"]
    n1_insecure = ca_result is not None and ca_result.get("n1_secure") is False
    if violation_count > 0 or overloaded > 0 or n1_insecure:
        health = "red"
    elif ld["buckets"]["heavy"] > 0:
        health = "amber"
    else:
        health = "green"
    return {
        "voltage_quality": vq,
        "loading": ld,
        "contingency_exposure": ce,
        "optimisation_benefit": ob,
        "overall_health": health,
    }
