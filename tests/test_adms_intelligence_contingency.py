"""WP-010 OA-045 — N-1 contingency analysis tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import (  # noqa: E402
    apply_update,
    fault_on_e1,
    operations_stack,
)

from services.adms_operational_intelligence import ContingencyAnalysisService  # noqa: E402


def test_n1_covers_conducting_edges_and_healthy_sources():
    view, _ = operations_stack()
    outcomes = ContingencyAnalysisService(view).evaluate_n1()
    ids = [outcome.contingency_id for outcome in outcomes]
    # tie1 is open (not conducting) and therefore not an N-1 element.
    assert len(outcomes) == 7
    assert "contingency:edge:tie1" not in ids
    assert {"contingency:edge:e1", "contingency:source:f1", "contingency:source:f2"} <= set(ids)


def test_impact_ranking_is_deterministic_most_severe_first():
    view, _ = operations_stack()
    outcomes = ContingencyAnalysisService(view).evaluate_n1()
    assert [outcome.contingency_id for outcome in outcomes] == [
        "contingency:edge:e1",
        "contingency:edge:e2",
        "contingency:edge:sw1",
        "contingency:source:f1",
        "contingency:edge:e3",
        "contingency:edge:e4",
        "contingency:source:f2",
    ]
    assert [outcome.severity_rank for outcome in outcomes] == list(range(1, 8))
    assert outcomes[0].de_energized_nodes == ("a", "b", "c")
    assert outcomes[0].lost_customer_count == 40
    assert outcomes[0].lost_load_kw == 100.0


def test_mitigation_candidates_identified():
    view, _ = operations_stack()
    outcomes = {
        outcome.contingency_id: outcome
        for outcome in ContingencyAnalysisService(view).evaluate_n1()
    }
    assert outcomes["contingency:edge:e1"].mitigation_tie_edges == ("tie1",)
    assert outcomes["contingency:source:f1"].mitigation_tie_edges == ("tie1",)
    assert outcomes["contingency:edge:e2"].mitigation_tie_edges == ()
    assert outcomes["contingency:edge:e4"].mitigation_tie_edges == ()


def test_resilience_assessment_summarises_exposure():
    view, _ = operations_stack()
    service = ContingencyAnalysisService(view)
    outcomes = service.evaluate_n1()
    assessment = service.resilience_assessment(outcomes)
    assert assessment.contingency_count == 7
    assert assessment.unmitigated_contingency_ids == (
        "contingency:edge:e2",
        "contingency:edge:e4",
    )
    assert assessment.worst_contingency_id == "contingency:edge:e1"
    assert assessment.max_lost_customer_count == 40
    assert assessment.max_lost_load_kw == 100.0


def test_single_element_evaluation():
    view, _ = operations_stack()
    outcome = ContingencyAnalysisService(view).evaluate_element("e3", "edge")
    assert outcome.de_energized_nodes == ("d", "e")
    assert outcome.lost_customer_count == 10
    assert outcome.severity_rank == 1
    assert outcome.mitigation_tie_edges == ("tie1",)


def test_unavailable_tie_is_not_a_mitigation():
    view, repository = operations_stack()
    apply_update(
        repository,
        update_id="u-tie1-unavailable",
        asset_id="tie1",
        asset_kind="edge",
        sequence=1,
        available=False,
    )
    outcomes = {
        outcome.contingency_id: outcome
        for outcome in ContingencyAnalysisService(view).evaluate_n1()
    }
    assert outcomes["contingency:edge:e1"].mitigation_tie_edges == ()
    assert outcomes["contingency:edge:e1"].has_mitigation is False


def test_n1_over_faulted_state_skips_dead_elements():
    view, repository = operations_stack()
    fault_on_e1(repository)
    outcomes = {
        outcome.contingency_id: outcome
        for outcome in ContingencyAnalysisService(view).evaluate_n1()
    }
    # e1 is already non-conducting, so it is no longer an N-1 element, and
    # failing sw1 in the already-dark region loses nothing further.
    assert "contingency:edge:e1" not in outcomes
    assert outcomes["contingency:edge:sw1"].de_energized_nodes == ()


def test_contingency_analysis_is_repeatable():
    view, _ = operations_stack()
    service = ContingencyAnalysisService(view)
    assert service.evaluate_n1() == service.evaluate_n1()
