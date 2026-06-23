"""ADMS P6-M9 unit tests — crew dispatch recommendation (pure, no DB/API).

Run:  python -m pytest tests/test_p6_crew_dispatch.py -q
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fastapi"))

from dms import crew_dispatch as cd  # noqa: E402


def _inferred(eid, cust, section):
    return {"probable_device": {"edge_id": eid}, "section_node": section,
            "section_name": section, "feeding_transformer": "TX1",
            "estimated_customers_affected": cust, "confidence": 1.0}


def _conting(eid, restored=None):
    return {"element": eid, "restored_by": restored or []}


def test_field_repair_ranked_above_remote_switch():
    inferred = [_inferred("E_TIE_OK", 50, "BUS-A"),   # restorable remotely
                _inferred("E_NO_TIE", 5, "BUS-B")]    # needs a crew
    conting = [_conting("E_TIE_OK", restored=["TIE1"]), _conting("E_NO_TIE")]
    res = cd.recommend(inferred, conting)
    top = res["candidates"][0]
    # the crew job ranks first even though it affects fewer customers
    assert top["probable_device"] == "E_NO_TIE"
    assert top["recommended_action"] == "dispatch_crew"
    assert top["priority_rank"] == 1
    assert res["crew_dispatch_count"] == 1 and res["remote_switch_count"] == 1


def test_remote_switch_carries_restoration_path():
    inferred = [_inferred("E_TIE_OK", 50, "BUS-A")]
    conting = [_conting("E_TIE_OK", restored=["TIE1"])]
    res = cd.recommend(inferred, conting)
    c = res["candidates"][0]
    assert c["restorable_via_tie"] is True
    assert c["restoration_path"] == ["TIE1"]
    assert c["recommended_action"] == "remote_switch"


def test_within_class_ranked_by_customers():
    inferred = [_inferred("E_A", 3, "BUS-A"), _inferred("E_B", 20, "BUS-B")]
    conting = [_conting("E_A"), _conting("E_B")]  # both field repairs
    res = cd.recommend(inferred, conting)
    assert [c["probable_device"] for c in res["candidates"]] == ["E_B", "E_A"]
    assert res["crew_dispatch_count"] == 2
