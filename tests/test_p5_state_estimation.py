"""ADMS P5-M2 unit tests — WLS distribution state estimation (pure, no DB/API).

Imports the engine directly (fastapi/dms/state_estimation.py) and exercises it on
small analytic feeders. Runs anywhere Python runs — no services required.

Run:  python -m pytest tests/test_p5_state_estimation.py -q
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

from dms import state_estimation as se  # noqa: E402
from dms import linalg  # noqa: E402


def _two_node(base_kw=50.0):
    nodes = [
        {"node_id": "SRC", "node_type": "substation", "nominal_kv": 0.415, "name": "src",
         "base_load_kw": 0.0, "base_load_kvar": 0.0},
        {"node_id": "L1", "node_type": "load", "nominal_kv": 0.415, "name": "load",
         "base_load_kw": base_kw, "base_load_kvar": 0.0},
    ]
    edges = [
        {"edge_id": "E1", "from_node": "SRC", "to_node": "L1", "edge_type": "line",
         "is_closed": True, "resistance_r_ohm": 0.1, "reactance_x_ohm": 0.0, "ampacity_a": 400},
    ]
    return nodes, edges


def test_linalg_solve_and_inverse():
    a = [[4.0, 1.0], [1.0, 3.0]]
    x = linalg.solve(a, [1.0, 2.0])
    # verify A x == b
    assert abs((4 * x[0] + 1 * x[1]) - 1.0) < 1e-9
    inv = linalg.inverse(a)
    prod = linalg.matmul(a, inv)
    assert abs(prod[0][0] - 1) < 1e-9 and abs(prod[0][1]) < 1e-9


def test_recovers_injection_and_voltage_from_power_meter():
    nodes, edges = _two_node(50.0)
    # analytic: R_pu = 0.1 / (0.415^2) = 0.5806; ΔV = R_pu * 50/1000 = 0.02903 pu
    zbase = 0.415 ** 2
    expected_v = 1.0 - (0.1 / zbase) * (50.0 / 1000.0)
    res = se.estimate(nodes, edges, {"L1": {"p_kw": 50.0}})
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    assert abs(l1["estimated_p_kw"] - 50.0) < 1.0
    assert abs(l1["estimated_voltage_pu"] - expected_v) < 0.003
    assert l1["monitored"] is True


def test_voltage_measurement_infers_load():
    nodes, edges = _two_node(50.0)
    zbase = 0.415 ** 2
    v_meas = 1.0 - (0.1 / zbase) * (50.0 / 1000.0)
    # only a voltage measurement (no power meter) — estimator should infer p≈50
    res = se.estimate(nodes, edges, {"L1": {"voltage_pu": round(v_meas, 4)}})
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    assert abs(l1["estimated_p_kw"] - 50.0) < 5.0


def test_missing_telemetry_uses_pseudo_and_lowers_confidence():
    nodes, edges = _two_node(50.0)
    res = se.estimate(nodes, edges, {})  # no measurements at all
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    assert l1["energized"] is True
    assert abs(l1["estimated_p_kw"] - 50.0) < 1e-6  # falls back to base load
    # unmonitored confidence is below the monitored floor
    monitored = se.estimate(nodes, edges, {"L1": {"p_kw": 50.0, "voltage_pu": 0.97}})
    l1m = next(n for n in monitored["nodes"] if n["node_id"] == "L1")
    assert l1m["confidence"] >= l1["confidence"]


def test_bad_data_detection_flags_inconsistent_voltage():
    nodes, edges = _two_node(50.0)
    # power meter says 50 kW (small drop) but voltage meter claims a huge sag → conflict
    res = se.estimate(nodes, edges, {"L1": {"p_kw": 50.0, "voltage_pu": 0.80}})
    assert res["bad_data"] is not None
    assert res["bad_data"]["kind"] in ("meter_v", "meter_p")
    assert res["max_normalized_residual"] > 3.0


def test_open_switch_de_energizes_subtree():
    nodes, edges = _two_node(50.0)
    edges[0]["edge_type"] = "switch"
    edges[0]["is_closed"] = False
    res = se.estimate(nodes, edges, {})
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    assert l1["energized"] is False
    assert l1["estimated_voltage_pu"] is None


def test_branch_flow_and_loading_reported():
    nodes, edges = _two_node(120.0)
    res = se.estimate(nodes, edges, {"L1": {"p_kw": 120.0}})
    b = next(x for x in res["branches"] if x["edge_id"] == "E1")
    assert abs(b["p_kw"] - 120.0) < 1.0
    assert b["current_a"] > 0 and b["loading_pct"] is not None
