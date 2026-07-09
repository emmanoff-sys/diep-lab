"""WP-010 OA-049 — decision explanation tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import fault_on_e1, operations_stack  # noqa: E402

from services.adms_operational_intelligence import (  # noqa: E402
    ContingencyAnalysisService,
    DecisionExplanationService,
    FaultLocationAssistanceService,
    RestorationOptimisationService,
    RuleEngine,
    default_operational_rules,
)
from services.adms_operations import IsolationBoundary, IsolationBoundaryService  # noqa: E402

REGION = ("a", "b", "c")


def _top_strategy(view, boundary=None):
    real_boundary = boundary or IsolationBoundaryService(view).analyze("outage-group:001", REGION)
    return RestorationOptimisationService(view).strategies(REGION, real_boundary)[0]


def test_strategy_explanation_carries_rationale_rules_evidence_constraints():
    view, repository = operations_stack()
    fault_on_e1(repository)
    strategy = _top_strategy(view)
    trace = RuleEngine(default_operational_rules()).evaluate(
        strategy.strategy_id,
        {
            "plan_safe": strategy.safe,
            "failed_safety_rules": (),
            "boundary_verified": True,
            "load_kw": strategy.candidate.restored_load_kw,
            "capacity_kw": strategy.candidate.path_capacity_kw,
            "max_feeder_load_kw": strategy.max_feeder_load_kw,
        },
    )
    explanation = DecisionExplanationService().explain_strategy(strategy, rule_trace=trace)
    assert "recommended" in explanation.summary
    assert "tie1" in explanation.summary
    assert any("40 customer(s)" in line for line in explanation.rationale)
    assert explanation.rule_ids == ("OI-R-001", "OI-R-002", "OI-R-003", "OI-R-004")
    assert any("supply path: f2 -> d" in item for item in explanation.evidence)
    assert any("path capacity 300.0 kW" in item for item in explanation.constraints)


def test_unsafe_strategy_explained_as_not_recommended():
    view, repository = operations_stack()
    fault_on_e1(repository)
    verified = IsolationBoundaryService(view).analyze("outage-group:001", REGION)
    unverified = IsolationBoundary(
        subject_id=verified.subject_id,
        isolation_points=verified.isolation_points,
        safe_isolation_edges=verified.safe_isolation_edges,
        verified=False,
        unisolated_nodes=("a",),
        diagnostics=verified.diagnostics,
    )
    strategy = _top_strategy(view, boundary=unverified)
    explanation = DecisionExplanationService().explain_strategy(strategy)
    assert "not recommended" in explanation.summary
    assert any("SR-003" in constraint for constraint in explanation.constraints)


def test_contingency_explanations_cover_mitigated_and_unmitigated():
    view, _ = operations_stack()
    outcomes = {
        outcome.contingency_id: outcome
        for outcome in ContingencyAnalysisService(view).evaluate_n1()
    }
    explainer = DecisionExplanationService()
    mitigated = explainer.explain_contingency(outcomes["contingency:edge:e1"])
    assert "severity rank 1" in mitigated.summary
    assert any("tie1" in line for line in mitigated.rationale)
    unmitigated = explainer.explain_contingency(outcomes["contingency:edge:e2"])
    assert any("no candidate mitigation" in line for line in unmitigated.rationale)


def test_fault_report_explanation_names_top_candidate():
    view, repository = operations_stack()
    fault_on_e1(repository)
    report = FaultLocationAssistanceService(view).analyze("outage-group:001", REGION)
    explanation = DecisionExplanationService().explain_fault_report(report)
    assert "e1" in explanation.summary
    assert "confidence 0.9" in explanation.summary
    assert explanation.decision_kind == "fault_location"


def test_explanations_are_deterministic():
    view, repository = operations_stack()
    fault_on_e1(repository)
    strategy = _top_strategy(view)
    explainer = DecisionExplanationService()
    assert explainer.explain_strategy(strategy) == explainer.explain_strategy(strategy)
