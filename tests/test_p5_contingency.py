"""ADMS P5-M5 unit tests — N-1 contingency analysis (pure, no DB/API).

Run:  python -m pytest tests/test_p5_contingency.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

from dms import contingency as ct  # noqa: E402


def _net():
    """SRC feeds J→L1 (no backup) and J→L2 (L2 also reachable from ALT via an open
    tie ET). So losing the L2 segment is restorable; losing the L1 segment is not."""
    nodes = [
        {"node_id": "SRC", "node_type": "substation", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "J", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "ALT", "node_type": "bus", "nominal_kv": 0.415, "phases": "ABC"},
        {"node_id": "L1", "node_type": "load", "nominal_kv": 0.415, "phases": "ABC",
         "base_load_kw": 40.0},
        {"node_id": "L2", "node_type": "load", "nominal_kv": 0.415, "phases": "ABC",
         "base_load_kw": 30.0},
    ]

    def e(eid, a, b, t, closed, r=0.03):
        return {"edge_id": eid, "from_node": a, "to_node": b, "edge_type": t,
                "is_switchable": t in ("switch", "tie"), "is_closed": closed,
                "resistance_r_ohm": r, "reactance_x_ohm": 0.01, "ampacity_a": 600,
                "phases": "ABC"}

    edges = [
        e("E1", "SRC", "J", "switch", True),
        e("E3", "SRC", "ALT", "switch", True),
        e("EA", "J", "L1", "line", True),
        e("EB", "J", "L2", "line", True),
        e("ET", "ALT", "L2", "tie", False),  # normally-open back-feed for L2
    ]
    loads = {"L1": {"a": complex(40 / 3, 0), "b": complex(40 / 3, 0), "c": complex(40 / 3, 0)},
             "L2": {"a": complex(10, 0), "b": complex(10, 0), "c": complex(10, 0)}}
    customers = {"L1": 2, "L2": 1}
    return nodes, edges, loads, customers


def _by_elem(res):
    return {c["element"]: c for c in res["contingencies"]}


def test_restorable_segment_via_tie():
    nodes, edges, loads, cust = _net()
    res = ct.analyze(nodes, edges, loads, cust)
    eb = _by_elem(res)["EB"]
    assert eb["classification"] == "restorable"
    assert "ET" in eb["restored_by"]
    assert eb["unserved_load_kw"] == 0


def test_unrestorable_segment_is_unserved():
    nodes, edges, loads, cust = _net()
    res = ct.analyze(nodes, edges, loads, cust)
    ea = _by_elem(res)["EA"]
    assert ea["classification"] == "unserved"
    assert ea["restored_by"] == []
    assert ea["unserved_load_kw"] == 40.0
    assert ea["unserved_customers"] == 2


def test_full_backfeed_via_single_tie():
    # Losing the source feed E1 strands the whole J subtree (J, L1, L2). Because
    # the intra-subtree edges stay closed, closing the single tie ET back-feeds the
    # entire subtree through L2→J→L1 — fully restorable, nothing unserved.
    nodes, edges, loads, cust = _net()
    res = ct.analyze(nodes, edges, loads, cust)
    e1 = _by_elem(res)["E1"]
    assert "ET" in e1["restored_by"]
    assert e1["unserved_load_kw"] == 0
    assert e1["classification"] == "restorable"


def test_not_n1_secure_and_ranked():
    nodes, edges, loads, cust = _net()
    res = ct.analyze(nodes, edges, loads, cust)
    assert res["n1_secure"] is False
    # severity-sorted; worst entries first
    sev = [c["severity"] for c in res["contingencies"]]
    assert sev == sorted(sev, reverse=True)
    assert res["worst"][0]["unserved_load_kw"] > 0
