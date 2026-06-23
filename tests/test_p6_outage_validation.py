"""ADMS P6-M8 unit tests — outage inference validation hooks (pure, no DB/API).

Run:  python -m pytest tests/test_p6_outage_validation.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

from dms import outage_validation as ov  # noqa: E402


def _inferred(eid, cust, section="BUS1"):
    return {"probable_device": {"edge_id": eid}, "section_node": section,
            "estimated_customers_affected": cust, "confidence": 1.0}


def _conting(eid, lost, restored=None, cls="unserved", viol=0):
    return {"element": eid, "lost_customers": lost, "restored_by": restored or [],
            "classification": cls, "post_violations": viol}


def test_consistent_inference_no_mismatch():
    res = ov.cross_check([_inferred("E1", 5)], [_conting("E1", 5)])
    assert res["consistent"] is True
    assert res["mismatch_count"] == 0
    assert "n1_confirms_unserved" in res["checks"][0]["flags"]


def test_customer_count_mismatch_flagged():
    res = ov.cross_check([_inferred("E1", 5)], [_conting("E1", 2)])
    assert res["consistent"] is False
    c = res["checks"][0]
    assert "customer_count_mismatch" in c["flags"] and c["mismatch"] is True


def test_device_not_in_n1_model():
    res = ov.cross_check([_inferred("EX", 5)], [_conting("E1", 5)])
    c = res["checks"][0]
    assert "inferred_device_not_in_n1_model" in c["flags"]
    assert res["consistent"] is False


def test_restorable_flag_is_informational_not_mismatch():
    res = ov.cross_check([_inferred("E1", 5)], [_conting("E1", 5, restored=["TIE"], cls="restorable")])
    c = res["checks"][0]
    assert "restorable_via_tie" in c["flags"]
    assert c["mismatch"] is False
    assert res["consistent"] is True
