"""ADMS P5-M3 unit tests — three-phase unbalanced power flow (pure, no DB/API).

Imports the engine directly (fastapi/dms/powerflow.py) and exercises it on small
analytic feeders. Runs anywhere Python runs — no services required.

Run:  python -m pytest tests/test_p5_powerflow.py -q
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_grid_analytics import powerflow as pf  # noqa: E402


def _two_node(r=0.1, x=0.0, ampacity=400, phases="ABC"):
    nodes = [
        {
            "node_id": "SRC",
            "node_type": "substation",
            "nominal_kv": 0.415,
            "name": "src",
            "phases": "ABC",
        },
        {
            "node_id": "L1",
            "node_type": "load",
            "nominal_kv": 0.415,
            "name": "load",
            "phases": phases,
        },
    ]
    edges = [
        {
            "edge_id": "E1",
            "from_node": "SRC",
            "to_node": "L1",
            "edge_type": "line",
            "is_closed": True,
            "resistance_r_ohm": r,
            "reactance_x_ohm": x,
            "ampacity_a": ampacity,
            "phases": phases,
        },
    ]
    return nodes, edges


def test_balanced_load_matches_analytic_drop():
    nodes, edges = _two_node(r=0.1, x=0.0)
    # 60 kW balanced (20/phase) → P_pu(3φ) = 0.06. R_pu = 0.1/0.415² = 0.5806.
    # Constant-power fixed point (resistive): V² − V + R_pu·P_pu = 0.
    loads = {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
    res = pf.solve(nodes, edges, loads)
    assert res["converged"] is True
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    r_pu = 0.1 / (0.415**2)
    expected = (1.0 + math.sqrt(1.0 - 4.0 * r_pu * 0.06)) / 2.0  # ≈ 0.9638
    assert abs(l1["v_min_pu"] - expected) < 0.002
    # balanced → ~zero unbalance
    assert l1["unbalance_pct"] < 0.1


def test_unbalanced_load_produces_unbalance():
    nodes, edges = _two_node(r=0.1, x=0.05)
    loads = {"L1": {"a": complex(45, 5), "b": complex(8, 1), "c": complex(8, 1)}}
    res = pf.solve(nodes, edges, loads)
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    # phase a is most loaded → lowest voltage; clear unbalance
    assert l1["phases"]["a"]["v_pu"] < l1["phases"]["b"]["v_pu"]
    assert l1["unbalance_pct"] > 0.5


def test_single_phase_lateral_only_has_its_phase():
    nodes, edges = _two_node(phases="A")
    loads = {"L1": {"a": complex(10, 0)}}
    res = pf.solve(nodes, edges, loads)
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    assert set(l1["phases"].keys()) == {"a"}
    assert l1["phases"]["a"]["v_pu"] < 1.0


def test_der_injection_raises_voltage():
    nodes, edges = _two_node(r=0.1, x=0.0)
    base = pf.solve(
        nodes, edges, {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
    )
    # negative load on phase a == DER export → that phase's voltage rises vs base
    der = pf.solve(
        nodes, edges, {"L1": {"a": complex(-20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
    )
    vb = next(n for n in base["nodes"] if n["node_id"] == "L1")["phases"]["a"]["v_pu"]
    vd = next(n for n in der["nodes"] if n["node_id"] == "L1")["phases"]["a"]["v_pu"]
    assert vd > vb


def test_voltage_violation_detected():
    nodes, edges = _two_node(r=0.6, x=0.3)  # high impedance + heavy load → deep sag
    loads = {"L1": {"a": complex(120, 30), "b": complex(120, 30), "c": complex(120, 30)}}
    res = pf.solve(nodes, edges, loads)
    assert any(v["type"] == "voltage" for v in res["violations"])


def test_thermal_violation_detected():
    nodes, edges = _two_node(r=0.05, x=0.02, ampacity=5)  # tiny ampacity
    loads = {"L1": {"a": complex(40, 0), "b": complex(40, 0), "c": complex(40, 0)}}
    res = pf.solve(nodes, edges, loads)
    assert any(v["type"] == "thermal" for v in res["violations"])


def test_open_switch_de_energizes():
    nodes, edges = _two_node()
    edges[0]["edge_type"] = "switch"
    edges[0]["is_closed"] = False
    res = pf.solve(nodes, edges, {"L1": {"a": complex(10, 0)}})
    l1 = next(n for n in res["nodes"] if n["node_id"] == "L1")
    assert l1["energized"] is False and l1["phases"] == {}


def test_converges_quickly():
    nodes, edges = _two_node()
    res = pf.solve(
        nodes, edges, {"L1": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)}}
    )
    assert res["converged"] and res["iterations"] < 20
