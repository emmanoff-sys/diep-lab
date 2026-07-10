"""ADMS P5-M6 unit tests — fault location (pure, no DB/API).

Run:  python -m pytest tests/test_p5_fault_location.py -q
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_grid_analytics import fault_location as fl  # noqa: E402


def _line_feeder():
    """SRC─E1─A─E2─B─E3─C, all 0.415 kV, cumulative R = 0.1 / 0.3 / 0.6 Ω."""
    nodes = [
        {"node_id": "SRC", "node_type": "substation", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "A", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "B", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "C", "node_type": "load", "nominal_kv": 0.415, "phases": "ABC"},
    ]

    def e(eid, a, b, r):
        return {
            "edge_id": eid,
            "from_node": a,
            "to_node": b,
            "edge_type": "line",
            "is_switchable": False,
            "is_closed": True,
            "resistance_r_ohm": r,
            "reactance_x_ohm": 0.0,
            "length_km": 1.0,
            "phases": "ABC",
        }

    edges = [e("E1", "SRC", "A", 0.1), e("E2", "A", "B", 0.2), e("E3", "B", "C", 0.3)]
    return nodes, edges


def _i_at(zmag):
    return (0.415 * 1000.0 / math.sqrt(3.0)) / zmag


def test_impedance_locates_correct_section():
    nodes, edges = _line_feeder()
    # cumulative Z at B = 0.3 Ω → fault current ≈ V_ln / 0.3
    i_meas = _i_at(0.3)
    res = fl.locate(nodes, edges, fault_current_a=i_meas)
    top = res["impedance_candidates"][0]
    assert top["section"] == "E2" and top["to_node"] == "B"
    assert top["error_pct"] < 1.0


def test_impedance_far_fault_lower_current():
    nodes, edges = _line_feeder()
    res = fl.locate(nodes, edges, fault_current_a=_i_at(0.6))  # at C
    assert res["impedance_candidates"][0]["to_node"] == "C"


def test_topological_from_outage_reports():
    nodes, edges = _line_feeder()
    # B and C dark → fault on the edge feeding the {B,C} subtree (E2)
    res = fl.locate(nodes, edges, outage_nodes=["B", "C"])
    assert res["topological"]["section"] == "E2"
    assert res["topological"]["matches_report"] is True


def test_combined_best_estimate():
    nodes, edges = _line_feeder()
    res = fl.locate(nodes, edges, fault_current_a=_i_at(0.3), outage_nodes=["B", "C"])
    assert res["best_estimate"]["method"] == "topological+impedance"
    assert res["best_estimate"]["section"] == "E2"
    assert res["best_estimate"]["distance_km"] is not None


def test_impedance_only_when_no_outage():
    nodes, edges = _line_feeder()
    res = fl.locate(nodes, edges, fault_current_a=_i_at(0.1))  # at A
    assert res["topological"] is None
    assert res["best_estimate"]["method"] == "impedance"
    assert res["best_estimate"]["section"] == "E1"
