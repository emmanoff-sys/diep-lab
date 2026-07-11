"""DIEP ADMS P5-M10 — Volt/VAR Optimisation engine (OA-127).

Evaluates reactive device dispatch configurations to improve voltage profile
and reduce network losses on radial distribution feeders. Consumes the
three-phase power flow engine (powerflow.solve) for objective evaluation;
does not implement any independent power flow mathematics.

Reactive device modelling (OA-126)
------------------------------------
Capacitive injection (capacitor banks, shunt compensation) is applied to the
base load dict before each power flow evaluation. Devices in the ON state
contribute a negative-Q load entry at their connection node:

    loads[node_id][phase] += complex(0, -q_injection_kvar / n_phases)

where q_injection_kvar > 0 for capacitive (leading) injection.

Optimisation approach
---------------------
Exhaustive enumeration of all 2^n on/off states for n reactive devices.
Feasible for distribution networks with ≤ 16 controllable devices; the
objective is evaluated by a full three-phase BFS power flow for each state.
The objective combines voltage violation count (heavy penalty), network
losses (kW), and RMS voltage deviation from the target.
"""

from __future__ import annotations

import math

from . import powerflow as pf

_PHASES = ("a", "b", "c")


def _phase_set(phases_str: str | None) -> list[str]:
    s = (phases_str or "ABC").lower()
    return [p for p in _PHASES if p in s]


def _apply_device_state(
    loads: dict,
    devices: list[dict],
    state: dict[str, bool],
) -> dict:
    """Return a new loads dict with reactive device injections applied.

    Devices in state True contribute their q_injection_kvar as a negative-Q
    load (capacitive) at the connection node, split equally across phases.
    Negative q_injection_kvar models inductive shunt absorption (positive Q).
    """
    result: dict[str, dict[str, complex]] = {nid: dict(phases) for nid, phases in loads.items()}
    for dev in devices:
        if not state.get(dev["device_id"], False):
            continue
        q_inject = float(dev.get("q_injection_kvar", 0.0))
        if q_inject == 0.0:
            continue
        phases = _phase_set(dev.get("phases"))
        if not phases:
            continue
        n_ph = len(phases)
        delta = complex(0.0, -q_inject / n_ph)
        nid = dev["node_id"]
        if nid not in result:
            result[nid] = {}
        for ph in phases:
            result[nid][ph] = result[nid].get(ph, 0j) + delta
    return result


def _score(
    pf_result: dict,
    v_target_pu: float,
    w_loss: float,
    w_viol: float,
) -> float:
    """Compute a scalar objective from a power flow result.

    Priority order: violations (w_viol × count) > losses (w_loss × kW) >
    voltage deviation (RMS from v_target_pu). Default weights give violations
    a 1000× advantage over loss minimisation.
    """
    n_viol = pf_result.get("violation_count", 0)
    loss_kw = float(pf_result.get("total_loss_kw") or 0.0)
    v_sq_dev = 0.0
    for n in pf_result.get("nodes", []):
        if n.get("energized"):
            v_avg = n.get("v_avg_pu")
            if v_avg is not None:
                v_sq_dev += (float(v_avg) - v_target_pu) ** 2
    return w_viol * n_viol + w_loss * loss_kw + math.sqrt(v_sq_dev)


def optimize(
    nodes: list[dict],
    edges: list[dict],
    loads: dict,
    devices: list[dict],
    options: dict | None = None,
) -> dict:
    """Enumerate reactive device configurations and return the optimal dispatch.

    Parameters
    ----------
    nodes:
        List of node dicts (``NodeSpec`` shape).
    edges:
        List of edge dicts (``EdgeSpec`` shape).
    loads:
        Base-case load dict ``{node_id: {phase: complex(P_kw, Q_kvar)}}``.
        Reactive device injections are overlaid on top of this dict for each
        configuration; the original dict is not mutated.
    devices:
        List of ``ReactiveDeviceSpec`` dicts, each with keys:
        ``device_id``, ``node_id``, ``phases``, ``q_injection_kvar``.
    options:
        ``VoltVARConfig`` overrides:
        ``v_target_pu`` (default 1.0), ``w_loss`` (default 1.0),
        ``w_viol`` (default 1000.0).

    Returns
    -------
    dict
        ``VoltVARResult``-shaped dict with keys:
        ``method``, ``devices_evaluated``, ``configurations_evaluated``,
        ``base_case``, ``optimal_state``, ``optimal_score``, ``optimal_case``,
        ``configurations``.
    """
    opt: dict = {"v_target_pu": 1.0, "w_loss": 1.0, "w_viol": 1000.0}
    if options:
        opt.update(options)
    v_tgt = float(opt["v_target_pu"])
    w_loss = float(opt["w_loss"])
    w_viol = float(opt["w_viol"])

    n_dev = len(devices)
    device_ids = [d["device_id"] for d in devices]

    base_pf = pf.solve(nodes, edges, loads)
    base_score = _score(base_pf, v_tgt, w_loss, w_viol)

    best_score = base_score
    best_state: dict[str, bool] = {did: False for did in device_ids}
    best_pf = base_pf

    configs: list[dict] = []
    for mask in range(1 << n_dev):
        state = {device_ids[i]: bool(mask & (1 << i)) for i in range(n_dev)}
        modified = _apply_device_state(loads, devices, state)
        pf_res = pf.solve(nodes, edges, modified)
        score = _score(pf_res, v_tgt, w_loss, w_viol)
        configs.append(
            {
                "device_state": dict(state),
                "score": round(score, 6),
                "violation_count": pf_res.get("violation_count", 0),
                "total_loss_kw": round(float(pf_res.get("total_loss_kw") or 0.0), 3),
                "converged": bool(pf_res.get("converged", False)),
            }
        )
        if score < best_score:
            best_score = score
            best_state = dict(state)
            best_pf = pf_res

    configs.sort(key=lambda c: c["score"])

    return {
        "method": "Volt/VAR exhaustive enumeration; three-phase power flow objective",
        "devices_evaluated": n_dev,
        "configurations_evaluated": len(configs),
        "base_case": {
            "violation_count": base_pf.get("violation_count", 0),
            "total_loss_kw": round(float(base_pf.get("total_loss_kw") or 0.0), 3),
            "converged": bool(base_pf.get("converged", False)),
        },
        "optimal_state": best_state,
        "optimal_score": round(best_score, 6),
        "optimal_case": {
            "violation_count": best_pf.get("violation_count", 0),
            "total_loss_kw": round(float(best_pf.get("total_loss_kw") or 0.0), 3),
            "converged": bool(best_pf.get("converged", False)),
        },
        "configurations": configs,
    }
