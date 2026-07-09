"""WP-009 OA-041/OA-042 — operator decision support and audit trail tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import fault_on_e1, operations_stack  # noqa: E402

from services.adms_operations import (  # noqa: E402
    OperationsAuditTrail,
    OperationsError,
    OperatorDecisionSupport,
    OutageDetectionService,
)

RECORDED_AT = "2026-07-08T11:00:00Z"


def _support_with_outage():
    view, repository = operations_stack()
    fault_on_e1(repository)
    audit = OperationsAuditTrail()
    support = OperatorDecisionSupport(view, audit=audit)
    group = OutageDetectionService(view).detect_all()[0]
    return support, group, audit


# --- OA-041: decision support ----------------------------------------------------
def test_outage_summary_reports_scope_and_causes():
    support, group, _ = _support_with_outage()
    summary = support.outage_summary(group)
    assert summary.subject_id == group.group_id
    assert summary.kinds == ("loss_of_supply",)
    assert summary.feeder_ids == ("f1",)
    assert summary.affected_node_count == 3
    assert summary.customer_count == 40
    assert "e1" in summary.candidate_cause_edges


def test_recommendation_composes_full_pipeline():
    support, group, _ = _support_with_outage()
    recommendation = support.recommend(group, recorded_at=RECORDED_AT)
    assert recommendation.recommendation_id == f"recommendation:{group.group_id}"
    assert recommendation.isolation_plan.subject_id == group.group_id
    assert [c.candidate_id for c in recommendation.restoration_candidates] == ["restore:tie1:f2"]
    assert len(recommendation.restoration_plans) == 1
    assert recommendation.restoration_plans[0].safe is True
    assert recommendation.explanations  # plain-language, non-empty


def test_recommendation_is_repeatable():
    support, group, _ = _support_with_outage()
    first = support.recommend(group, recorded_at=RECORDED_AT)
    second = support.recommend(group, recorded_at=RECORDED_AT)
    assert first.summary == second.summary
    assert first.isolation_plan == second.isolation_plan
    assert first.restoration_candidates == second.restoration_candidates
    assert first.explanations == second.explanations


def test_advisories_flag_non_switchable_boundary():
    support, group, _ = _support_with_outage()
    recommendation = support.recommend(group, recorded_at=RECORDED_AT)
    messages = [advisory.message for advisory in recommendation.advisories]
    assert any("not switchable" in message for message in messages)


def test_explanations_mention_restoration_option():
    support, group, _ = _support_with_outage()
    recommendation = support.recommend(group, recorded_at=RECORDED_AT)
    text = "\n".join(recommendation.explanations)
    assert "tie1" in text
    assert "f2" in text
    assert "40 customer(s)" in text


# --- OA-042: audit trail ----------------------------------------------------------
def test_recommendation_records_traceable_audit_chain():
    support, group, audit = _support_with_outage()
    support.recommend(group, recorded_at=RECORDED_AT)
    history = audit.history(subject_id=group.group_id)
    kinds = [record.kind for record in history]
    assert kinds == ["outage_detected", "plan_generated", "recommendation_issued"]
    assert [record.sequence for record in history] == [1, 2, 3]
    trace = audit.trace(history[2].record_id)
    assert [record.record_id for record in trace] == [
        history[0].record_id,
        history[1].record_id,
        history[2].record_id,
    ]


def test_operator_acknowledgement_links_to_recommendation():
    support, group, audit = _support_with_outage()
    support.recommend(group, recorded_at=RECORDED_AT)
    recommendation_record = audit.history(kind="recommendation_issued")[0]
    ack = audit.acknowledge(
        recommendation_record.record_id,
        actor="operator-jane",
        recorded_at="2026-07-08T11:05:00Z",
        note="isolation approved for execution by field crew",
    )
    assert ack.kind == "operator_acknowledgement"
    assert ack.related_record_ids == (recommendation_record.record_id,)
    assert ack.payload["note"] == "isolation approved for execution by field crew"
    assert ack in audit.trace(recommendation_record.record_id)


def test_related_records_must_exist():
    audit = OperationsAuditTrail()
    with pytest.raises(OperationsError):
        audit.record(
            kind="plan_generated",
            subject_id="subject:x",
            actor="decision-support",
            recorded_at=RECORDED_AT,
            related_record_ids=("decision:999999",),
        )


def test_unknown_record_lookup_raises():
    audit = OperationsAuditTrail()
    with pytest.raises(OperationsError):
        audit.require("decision:000001")


def test_history_filters_by_kind_and_subject():
    support, group, audit = _support_with_outage()
    support.recommend(group, recorded_at=RECORDED_AT)
    assert len(audit.history(kind="plan_generated")) == 1
    assert audit.history(subject_id="other") == ()
    assert len(audit.history()) == 3
