"""WP-009 OA-043 — end-to-end operations integration tests.

Exercises the full stack in one flow: WP-008 operational events drive state,
WP-009 detects the outage, analyses isolation, generates plans, finds
restoration options, issues a traceable recommendation — and the WP-007/
WP-008 layers keep behaving unchanged (regression guard)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402

from services.adms_operational_state import (  # noqa: E402
    OperationalEvent,
    OperationalEventProcessor,
    OperationalStateValidator,
    StateUpdateEngine,
)
from services.adms_operations import (  # noqa: E402
    OperationsAuditTrail,
    OperatorDecisionSupport,
    OutageDetectionService,
    SwitchingPlanService,
)
from services.adms_topology_services import OutageImpactService  # noqa: E402

RECORDED_AT = "2026-07-08T12:00:00Z"


def _processor(view, repository) -> OperationalEventProcessor:
    validator = OperationalStateValidator(view.topology)
    return OperationalEventProcessor(StateUpdateEngine(repository, validator))


def _drive_fault_via_events(view, repository):
    """Fault arrives as a WP-008 operational event, not a direct update."""
    result = _processor(view, repository).process(
        OperationalEvent(
            event_id="evt-e1-trip",
            event_type="breaker_operation",
            asset_id="e1",
            asset_kind="edge",
            sequence=1,
            observed_at="2026-07-08T11:58:00Z",
            actor="scada-sim",
            payload={"status": "open", "available": False},
        )
    )
    assert result.update_result.accepted is True
    return view


def test_end_to_end_outage_to_recommendation():
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)

    audit = OperationsAuditTrail()
    support = OperatorDecisionSupport(view, audit=audit)

    # Detect
    groups = OutageDetectionService(view).detect_all()
    assert len(groups) == 1
    group = groups[0]
    assert group.affected_nodes == ("a", "b", "c")

    # Recommend (isolate + restore)
    recommendation = support.recommend(group, recorded_at=RECORDED_AT)
    assert recommendation.isolation_plan.safe is True
    assert recommendation.restoration_candidates[0].tie_edge_id == "tie1"
    restoration_plan = recommendation.restoration_plans[0]
    assert restoration_plan.safe is True
    assert [(s.action, s.edge_id) for s in restoration_plan.steps] == [("close", "tie1")]

    # Preconditions evaluable against live state
    switching = SwitchingPlanService(view)
    results = switching.validate_preconditions(restoration_plan)
    assert all(result.satisfied for result in results)

    # Traceable audit chain + operator acknowledgement
    issued = audit.history(kind="recommendation_issued")[0]
    ack = audit.acknowledge(
        issued.record_id, actor="operator-jane", recorded_at="2026-07-08T12:05:00Z"
    )
    assert len(audit.trace(issued.record_id)) == 4
    assert ack.sequence == 4


def test_pipeline_is_deterministic_end_to_end():
    view_a, repo_a = operations_stack()
    view_b, repo_b = operations_stack()
    _drive_fault_via_events(view_a, repo_a)
    _drive_fault_via_events(view_b, repo_b)
    support_a = OperatorDecisionSupport(view_a)
    support_b = OperatorDecisionSupport(view_b)
    group_a = OutageDetectionService(view_a).detect_all()[0]
    group_b = OutageDetectionService(view_b).detect_all()[0]
    assert group_a == group_b
    assert support_a.recommend(group_a) == support_b.recommend(group_b)


def test_wp007_outage_impact_unchanged_regression():
    """WP-007's static outage impact service still answers as before."""
    view, _ = operations_stack()
    impact = OutageImpactService(view.topology).analyze_edge_outage("e2")
    assert "c" in impact.affected_nodes
    assert impact.customer_count >= 40


def test_wp008_state_history_unchanged_regression():
    """WP-008 history/audit semantics untouched by WP-009 consumption."""
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)
    history = repository.history("e1")
    assert len(history) == 1
    state = repository.get_state("e1", asset_kind="edge")
    assert state is not None
    assert state.available is False


def test_no_restoration_available_is_reported_not_invented():
    """With the tie unavailable, the recommendation must say so honestly."""
    view, repository = operations_stack()
    _drive_fault_via_events(view, repository)
    _processor(view, repository).process(
        OperationalEvent(
            event_id="evt-tie1-fail",
            event_type="alarm",
            asset_id="tie1",
            asset_kind="edge",
            sequence=2,
            observed_at="2026-07-08T11:59:00Z",
            actor="scada-sim",
            payload={"available": False},
        )
    )
    support = OperatorDecisionSupport(view)
    group = OutageDetectionService(view).detect_all()[0]
    recommendation = support.recommend(group)
    assert recommendation.restoration_candidates == ()
    assert recommendation.restoration_plans == ()
    assert any(
        "no restoration path" in advisory.message.lower() for advisory in recommendation.advisories
    )
