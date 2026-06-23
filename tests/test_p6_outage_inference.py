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


def test_se_corroboration_flag():
    nodes, edges, cust = _net()
    # M1 dark and M2's state estimation also reads it dead → corroborated
    res = oi.infer(nodes, edges, ["M1"], cust, se_dead_nodes=["M1"])
    assert res["inferred_outages"][0]["corroborated_by_se"] is True
    # without an SE-dead reading at the section, no corroboration
    res2 = oi.infer(nodes, edges, ["M1"], cust, se_dead_nodes=[])
    assert res2["inferred_outages"][0]["corroborated_by_se"] is False
    # default (no SE input) → flags off, never overrides AMI inference
    res3 = oi.infer(nodes, edges, ["M1"], cust)
    assert res3["inferred_outages"][0]["corroborated_by_se"] is False
    assert res3["silent_failure_suspected"] is False


def test_silent_failure_detected_by_se():
    nodes, edges, cust = _net()
    # M1 reported a last-gasp; M2 did NOT, but SE reads it dead → silent failure
    res = oi.infer(nodes, edges, ["M1"], cust, se_dead_nodes=["M1", "M2"])
    assert res["silent_failure_suspected"] is True
    assert res["silent_failure_nodes"] == ["M2"]


def _radial_with_tripped_switch(is_closed):
    """SRC→TX→M; E1 (SRC→TX) is a switchable protective device. When is_closed=False
    it has tripped open, de-energizing TX+M (outage reflected in topology)."""
    nodes = [
        {"node_id": "SRC", "node_type": "substation", "nominal_kv": 11, "name": "SRC", "phases": "ABC"},
        {"node_id": "TX", "node_type": "transformer", "nominal_kv": 0.415, "name": "TX", "phases": "ABC"},
        {"node_id": "M", "node_type": "meter", "nominal_kv": 0.415, "name": "M", "phases": "ABC"},
    ]
    edges = [
        {"edge_id": "E1", "from_node": "SRC", "to_node": "TX", "edge_type": "switch",
         "is_switchable": True, "normally_closed": True, "is_closed": is_closed,
         "resistance_r_ohm": 0.05, "reactance_x_ohm": 0.02, "phases": "ABC"},
        {"edge_id": "E2", "from_node": "TX", "to_node": "M", "edge_type": "line",
         "is_switchable": False, "normally_closed": True, "is_closed": True,
         "resistance_r_ohm": 0.03, "reactance_x_ohm": 0.01, "phases": "ABC"},
    ]
    return nodes, edges, {"M": 3}


def test_structural_fallback_when_protective_device_open():
    # E1 tripped open → M is outside the energized tree. SE reads the de-energized
    # section dead (genuine collapse). M7 must still yield an inference (structural
    # pass) with the open device E1, and the SE corroboration flag must fire.
    nodes, edges, cust = _radial_with_tripped_switch(is_closed=False)
    res = oi.infer(nodes, edges, ["M"], cust, se_dead_nodes=["TX", "M"])
    assert res["outage_count"] == 1
    o = res["inferred_outages"][0]
    assert o["source"] == "structural"
    assert o["probable_device"]["edge_id"] == "E1"          # the open protective device
    assert o["feeding_transformer"] == "TX"
    assert o["estimated_customers_affected"] == 3
    assert o["corroborated_by_se"] is True                  # SE agrees the section is dead


def test_energized_pass_stays_primary_when_device_closed():
    # Same network, E1 closed (outage not reflected) → the energized pass handles it.
    nodes, edges, cust = _radial_with_tripped_switch(is_closed=True)
    res = oi.infer(nodes, edges, ["M"], cust, se_dead_nodes=["M"])
    o = res["inferred_outages"][0]
    assert o["source"] == "energized"
    assert o["probable_device"]["edge_id"] == "E2"          # localizes to the meter's section


def test_two_separate_outages_ranked():
    nodes, edges, cust = _net()
    res = oi.infer(nodes, edges, ["M1", "M4"], cust)
    assert res["outage_count"] == 2
    # ranked by estimated customers: M4 (5) before M1 (2)
    assert res["inferred_outages"][0]["dark_meters"] == ["M4"]
    assert res["inferred_outages"][0]["estimated_customers_affected"] == 5
    assert res["inferred_outages"][1]["dark_meters"] == ["M1"]
