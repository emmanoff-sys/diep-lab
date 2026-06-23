"""ADMS P6-M7 unit tests — outage detection / inference (pure, no DB/API).

Run:  python -m pytest tests/test_p6_outage_inference.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

from dms import outage_inference as oi  # noqa: E402


def _net():
    """SRC→FDR, two transformers each feeding a bus + meters:
        TX1→BUS1→{M1,M2,M3},  TX2→BUS2→{M4}."""
    def n(nid, t, kv=0.415):
        return {"node_id": nid, "node_type": t, "nominal_kv": kv, "name": nid, "phases": "ABC"}

    def e(eid, a, b, t="line", sw=False):
        return {"edge_id": eid, "from_node": a, "to_node": b, "edge_type": t,
                "is_switchable": sw, "is_closed": True, "resistance_r_ohm": 0.02,
                "reactance_x_ohm": 0.01, "phases": "ABC"}

    nodes = [n("SRC", "substation", 33), n("FDR", "feeder", 11),
             n("TX1", "transformer"), n("TX2", "transformer"),
             n("BUS1", "bus"), n("BUS2", "bus"),
             n("M1", "meter"), n("M2", "meter"), n("M3", "meter"), n("M4", "meter")]
    edges = [
        e("E1", "SRC", "FDR"),
        e("ESW1", "FDR", "TX1", "switch", True),
        e("ESW2", "FDR", "TX2", "switch", True),
        e("ET1", "TX1", "BUS1", "transformer"),
        e("ET2", "TX2", "BUS2", "transformer"),
        e("E-M1", "BUS1", "M1"), e("E-M2", "BUS1", "M2"), e("E-M3", "BUS1", "M3"),
        e("E-M4", "BUS2", "M4"),
    ]
    customers = {"M1": 2, "M2": 3, "M3": 1, "M4": 5}
    return nodes, edges, customers


def test_whole_transformer_outage():
    nodes, edges, cust = _net()
    res = oi.infer(nodes, edges, ["M1", "M2", "M3"], cust)
    assert res["outage_count"] == 1
    o = res["inferred_outages"][0]
    # LCA of the three meters is BUS1 → probable device is its transformer feed ET1
    assert o["section_node"] == "BUS1"
    assert o["probable_device"]["edge_id"] == "ET1"
    assert o["feeding_transformer"] == "TX1"
    assert o["estimated_customers_affected"] == 6   # 2+3+1
    assert o["confidence"] == 1.0                   # all section meters dark


def test_single_meter_localizes_to_its_section():
    nodes, edges, cust = _net()
    res = oi.infer(nodes, edges, ["M1"], cust)
    o = res["inferred_outages"][0]
    assert o["section_node"] == "M1"
    assert o["probable_device"]["edge_id"] == "E-M1"
    assert o["estimated_customers_affected"] == 2


def test_partial_dark_lowers_confidence():
    nodes, edges, cust = _net()
    res = oi.infer(nodes, edges, ["M1", "M2"], cust)  # M3 still up
    o = res["inferred_outages"][0]
    assert o["section_node"] == "BUS1"          # LCA of M1,M2 is still BUS1
    assert o["estimated_customers_affected"] == 6  # full section (over-broad)
    assert round(o["confidence"], 2) == round(2 / 3, 2)  # only 2 of 3 meters dark


def test_two_separate_outages_ranked():
    nodes, edges, cust = _net()
    res = oi.infer(nodes, edges, ["M1", "M4"], cust)
    assert res["outage_count"] == 2
    # ranked by estimated customers: M4 (5) before M1 (2)
    assert res["inferred_outages"][0]["dark_meters"] == ["M4"]
    assert res["inferred_outages"][0]["estimated_customers_affected"] == 5
    assert res["inferred_outages"][1]["dark_meters"] == ["M1"]
