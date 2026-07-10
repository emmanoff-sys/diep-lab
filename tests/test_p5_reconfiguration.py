"""ADMS P5-M4 unit tests — optimal network reconfiguration (pure, no DB/API).

Run:  python -m pytest tests/test_p5_reconfiguration.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_grid_analytics import reconfiguration as rc  # noqa: E402


def _two_path_net():
    """SRC feeds load L by two paths: a high-impedance closed sectionalizer (EA)
    and a low-impedance normally-open tie (EB). Min-loss config reroutes to EB."""
    nodes = [
        {"node_id": "SRC", "node_type": "substation", "nominal_kv": 0.415, "phases": "ABC"},
        # N1 carries its own load, so opening E1 would shed it (infeasible) — this
        # makes the EA-open / EB-close reroute the unique min-loss solution.
        {
            "node_id": "N1",
            "node_type": "load",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "base_load_kw": 9.0,
            "base_load_kvar": 0.0,
        },
        {"node_id": "N2", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {
            "node_id": "L",
            "node_type": "load",
            "nominal_kv": 0.415,
            "phases": "ABC",
            "base_load_kw": 60.0,
            "base_load_kvar": 0.0,
        },
    ]
    edges = [
        {
            "edge_id": "E1",
            "from_node": "SRC",
            "to_node": "N1",
            "edge_type": "switch",
            "is_switchable": True,
            "is_closed": True,
            "resistance_r_ohm": 0.02,
            "reactance_x_ohm": 0.01,
            "ampacity_a": 600,
            "phases": "ABC",
        },
        {
            "edge_id": "E2",
            "from_node": "SRC",
            "to_node": "N2",
            "edge_type": "switch",
            "is_switchable": True,
            "is_closed": True,
            "resistance_r_ohm": 0.02,
            "reactance_x_ohm": 0.01,
            "ampacity_a": 600,
            "phases": "ABC",
        },
        {
            "edge_id": "EA",
            "from_node": "N1",
            "to_node": "L",
            "edge_type": "switch",
            "is_switchable": True,
            "is_closed": True,
            "resistance_r_ohm": 0.50,
            "reactance_x_ohm": 0.10,
            "ampacity_a": 600,
            "phases": "ABC",
        },
        {
            "edge_id": "EB",
            "from_node": "N2",
            "to_node": "L",
            "edge_type": "tie",
            "is_switchable": True,
            "is_closed": False,
            "resistance_r_ohm": 0.05,
            "reactance_x_ohm": 0.02,
            "ampacity_a": 600,
            "phases": "ABC",
        },
    ]
    loads = {
        "L": {"a": complex(20, 0), "b": complex(20, 0), "c": complex(20, 0)},
        "N1": {"a": complex(3, 0), "b": complex(3, 0), "c": complex(3, 0)},
    }
    return nodes, edges, loads


def test_recommends_lower_loss_reroute():
    nodes, edges, loads = _two_path_net()
    res = rc.recommend(nodes, edges, loads)
    assert res["current"] is not None and res["recommended"] is not None
    # the optimum reroutes load off the high-R sectionalizer onto the low-R tie
    assert res["action_required"] is True
    actions = {(s["edge_id"], s["action"]) for s in res["switching_plan"]}
    assert ("EB", "close") in actions
    assert ("EA", "open") in actions
    assert res["loss_reduction_kw"] > 0
    assert res["recommended"]["loss_kw"] < res["current"]["loss_kw"]


def test_feasible_configs_keep_load_served():
    nodes, edges, loads = _two_path_net()
    res = rc.recommend(nodes, edges, loads)
    # every feasible config keeps L served & radial; recommended has no violation
    assert res["feasible_count"] >= 1
    assert res["recommended"]["violations"] == 0


def test_already_optimal_no_action():
    nodes, edges, loads = _two_path_net()
    # start in the optimal config (EA open, EB closed) — engine should propose nothing
    for e in edges:
        if e["edge_id"] == "EA":
            e["is_closed"] = False
        if e["edge_id"] == "EB":
            e["is_closed"] = True
    res = rc.recommend(nodes, edges, loads)
    assert res["action_required"] is False
    assert res["switching_plan"] == []


def test_reconfigurable_excludes_islanding_breaker():
    nodes, edges, loads = _two_path_net()
    edges.append(
        {
            "edge_id": "CB",
            "from_node": "N1",
            "to_node": "L",
            "edge_type": "switch",
            "is_switchable": True,
            "is_closed": True,
            "resistance_r_ohm": 0.01,
            "reactance_x_ohm": 0.0,
            "ampacity_a": 600,
            "phases": "ABC",
            "attrs": {"role": "islanding_breaker"},
        }
    )
    res = rc.recommend(nodes, edges, loads)
    assert "CB" not in res["reconfigurable_switches"]
