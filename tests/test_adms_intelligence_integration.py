"""WP-010 OA-051 — operational intelligence integration tests.

Exercises the full five-layer stack: a WP-008 operational event drives
state, WP-009 detects the outage, WP-010 assesses it (fault location,
optimised restoration strategies, rule trace, explanations) — while the
WP-006/WP-007/WP-008/WP-009 layers keep behaving unchanged."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402

from services.adms_operational_intelligence import (  # noqa: E402
    ContingencyAnalysisService,
    HistoricalEvent,
    OperationalIntelligenceService,
    Scenario,
    ScenarioAction,
    ScenarioSimulationService,
)
from services.adms_operational_state import (  # noqa: E402
    OperationalEvent,
    OperationalEventProcessor,
    OperationalStateValidator,
    StateUpdateEngine,
)
from services.adms_operations import (  # noqa: E402
    OperatorDecisionSupport,
    OutageDetectionService,
)
from services.adms_topology_services import OutageImpactService  # noqa: E402

HISTORY = (HistoricalEvent(asset_id="e1", kind="breaker_trip", observed_at="2026-07-01T00:00:00Z"),)


def _processor(view, repository) -> OperationalEventProcessor:
    validator = OperationalStateValidator(view.topology)
    return OperationalEventProcessor(StateUpdateEngine(repository, validator))


def _drive_fault_via_events(view, repository, *, sequence: int = 1, asset_id: str = "e1"):
    result = _processor(view, repository).process(
        OperationalEvent(
            event_id=f"evt-{asset_id}-trip",
            event_type="breaker_operation",
            asset_id=asset_id,
            asset_kind="edge",
            sequence=sequence,
            observed_at=f"2026-07-09T11:5{sequence}:00Z",
            actor="scada-sim",
            payload={"status": "open", "available": False},
        )
    )
    assert result.update_result.accepted is True


def test_end_to_end_event_to_intelligence_assessment():
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)

    group = OutageDetectionService(view).detect_all()[0]
    assessment = OperationalIntelligenceService(view, history=HISTORY).assess(group)

    assert assessment.assessment_id == f"assessment:{group.group_id}"
    assert assessment.fault_report.candidates[0].edge_id == "e1"
    assert assessment.fault_report.candidates[0].confidence == 1.0
    strategy = assessment.strategies[0]
    assert strategy.strategy_id == "strategy:restore:tie1:f2"
    assert strategy.safe is True and strategy.rank == 1
    assert assessment.rule_trace.passed is True
    assert assessment.rule_trace.evaluation_id == "rule-evaluation:strategy:restore:tie1:f2"
    assert len(assessment.rule_trace.outcomes) == 4
    assert any("close tie1" in explanation.summary for explanation in assessment.explanations)


def test_assessment_is_deterministic_across_stacks():
    view_a, repo_a = operations_stack()
    view_b, repo_b = operations_stack()
    _drive_fault_via_events(view_a, repo_a)
    _drive_fault_via_events(view_b, repo_b)
    group_a = OutageDetectionService(view_a).detect_all()[0]
    group_b = OutageDetectionService(view_b).detect_all()[0]
    assessment_a = OperationalIntelligenceService(view_a, history=HISTORY).assess(group_a)
    assessment_b = OperationalIntelligenceService(view_b, history=HISTORY).assess(group_b)
    assert assessment_a == assessment_b


def test_honest_assessment_when_no_restoration_exists():
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)
    _processor(view, repository).process(
        OperationalEvent(
            event_id="evt-tie1-fail",
            event_type="alarm",
            asset_id="tie1",
            asset_kind="edge",
            sequence=2,
            observed_at="2026-07-09T11:59:00Z",
            actor="scada-sim",
            payload={"available": False},
        )
    )
    group = OutageDetectionService(view).detect_all()[0]
    assessment = OperationalIntelligenceService(view).assess(group)
    assert assessment.strategies == ()
    assert assessment.rule_trace.outcomes == ()
    assert any(
        "no restoration strategy is currently available" in explanation.summary
        for explanation in assessment.explanations
    )


def test_scenario_simulation_agrees_with_recommended_strategy():
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)
    group = OutageDetectionService(view).detect_all()[0]
    assessment = OperationalIntelligenceService(view).assess(group)
    tie = assessment.strategies[0].candidate.tie_edge_id
    outcome = ScenarioSimulationService(view).simulate(
        Scenario(
            scenario_id="scenario:apply-strategy",
            description="apply the recommended restoration strategy",
            actions=(ScenarioAction("close_switch", tie),),
        )
    )
    assert outcome.re_energized_nodes == group.affected_nodes


def test_contingency_analysis_over_live_stack():
    view, _ = operations_stack()
    outcomes = ContingencyAnalysisService(view).evaluate_n1()
    assert outcomes[0].contingency_id == "contingency:edge:e1"
    assert outcomes[0].mitigation_tie_edges == ("tie1",)


def test_lower_layers_unchanged_regression():
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)

    # WP-009 decision support still answers as before.
    group = OutageDetectionService(view).detect_all()[0]
    recommendation = OperatorDecisionSupport(view).recommend(group)
    assert recommendation.isolation_plan.safe is True
    assert recommendation.restoration_candidates[0].tie_edge_id == "tie1"

    # WP-008 state history is untouched by WP-010 analysis.
    OperationalIntelligenceService(view).assess(group)
    assert len(repository.history("e1")) == 1

    # WP-007 static outage impact still answers as before.
    impact = OutageImpactService(view.topology).analyze_edge_outage("e2")
    assert "c" in impact.affected_nodes
    assert impact.customer_count >= 40
