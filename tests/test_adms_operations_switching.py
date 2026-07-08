"""WP-009 OA-039 — switching plan generation tests."""

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

from services.adms_operations import (  # noqa: E402
    IsolationBoundary,
    IsolationBoundaryService,
    RestorationCandidate,
    SwitchingPlanService,
)


def _boundary_for(view, subject: str, region: tuple[str, ...]) -> IsolationBoundary:
    return IsolationBoundaryService(view).analyze(subject, region)


def test_isolation_plan_opens_closed_safe_points_in_order():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "subject:bc", ("b", "c"))
    plan = SwitchingPlanService(view).build_isolation_plan(boundary)
    assert plan.plan_id == "plan:isolate:subject:bc"
    # sw1 is closed and must be opened; tie1 is already open (diagnostic).
    assert [(step.action, step.edge_id) for step in plan.steps] == [("open", "sw1")]
    assert [step.step_number for step in plan.steps] == [1]
    assert any("tie1 is already open" in diagnostic for diagnostic in plan.diagnostics)
    assert plan.safe is True


def test_rollback_reverses_isolation_steps():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "subject:bc", ("b", "c"))
    plan = SwitchingPlanService(view).build_isolation_plan(boundary)
    assert [(step.action, step.edge_id) for step in plan.rollback_steps] == [("close", "sw1")]
    assert plan.rollback_steps[0].expected_state_before == "open"


def test_restoration_plan_closes_tie_with_preconditions():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "outage-group:001", ("a", "b", "c"))
    candidate = RestorationCandidate(
        candidate_id="restore:tie1:f2",
        tie_edge_id="tie1",
        supply_feeder_id="f2",
        supply_path_nodes=("f2", "d"),
        restored_nodes=("a", "b", "c"),
        restored_load_kw=100.0,
        restored_customer_count=40,
        path_capacity_kw=300.0,
        capacity_ok=True,
    )
    plan = SwitchingPlanService(view).build_restoration_plan(candidate, boundary)
    assert [(step.action, step.edge_id) for step in plan.steps] == [("close", "tie1")]
    assert plan.safe is True
    assert [(step.action, step.edge_id) for step in plan.rollback_steps] == [("open", "tie1")]
    assert any("verified" in condition for condition in plan.steps[0].preconditions)


def test_close_refused_when_boundary_not_verified():
    view, repository = operations_stack()
    fault_on_e1(repository)
    verified = _boundary_for(view, "outage-group:001", ("a", "b", "c"))
    unverified = IsolationBoundary(
        subject_id=verified.subject_id,
        isolation_points=verified.isolation_points,
        safe_isolation_edges=verified.safe_isolation_edges,
        verified=False,
        unisolated_nodes=("a",),
        diagnostics=verified.diagnostics,
    )
    candidate = RestorationCandidate(
        candidate_id="restore:tie1:f2",
        tie_edge_id="tie1",
        supply_feeder_id="f2",
        supply_path_nodes=("f2", "d"),
        restored_nodes=("a", "b", "c"),
        restored_load_kw=100.0,
        restored_customer_count=40,
        path_capacity_kw=300.0,
        capacity_ok=True,
    )
    plan = SwitchingPlanService(view).build_restoration_plan(candidate, unverified)
    assert plan.safe is False
    failed_rules = {failure.rule_id for failure in plan.safety.failures}
    assert "SR-003" in failed_rules


def test_close_refused_when_target_already_energised():
    """SR-004: closing into an energised region is a parallel feed."""
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "outage-group:001", ("a", "b", "c"))
    candidate = RestorationCandidate(
        candidate_id="restore:tie1:f2",
        tie_edge_id="tie1",
        supply_feeder_id="f2",
        supply_path_nodes=("f2", "d"),
        restored_nodes=("d", "e"),  # already-energised nodes
        restored_load_kw=50.0,
        restored_customer_count=10,
        path_capacity_kw=300.0,
        capacity_ok=True,
    )
    plan = SwitchingPlanService(view).build_restoration_plan(candidate, boundary)
    assert plan.safe is False
    failed_rules = {failure.rule_id for failure in plan.safety.failures}
    assert "SR-004" in failed_rules


def test_preconditions_fail_on_unavailable_device():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "subject:bc", ("b", "c"))
    service = SwitchingPlanService(view)
    plan = service.build_isolation_plan(boundary)
    apply_update(
        repository,
        update_id="u-sw1-unavailable",
        asset_id="sw1",
        asset_kind="edge",
        sequence=2,
        available=False,
    )
    results = service.validate_preconditions(plan)
    assert [result.satisfied for result in results] == [False]
    assert "unavailable" in results[0].detail


def test_preconditions_fail_on_state_mismatch():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "subject:bc", ("b", "c"))
    service = SwitchingPlanService(view)
    plan = service.build_isolation_plan(boundary)
    apply_update(
        repository,
        update_id="u-sw1-opened",
        asset_id="sw1",
        asset_kind="edge",
        sequence=2,
        switch_status="open",
    )
    results = service.validate_preconditions(plan)
    assert [result.satisfied for result in results] == [False]
    assert "expected closed but is open" in results[0].detail


def test_plans_never_operate_non_switchable_devices():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = _boundary_for(view, "outage-group:001", ("a", "b", "c"))
    plan = SwitchingPlanService(view).build_isolation_plan(boundary)
    operated = {step.edge_id for step in plan.steps}
    assert "e1" not in operated  # non-switchable boundary edge
    sr_002 = next(r for r in plan.safety.results if r.rule_id == "SR-002")
    assert sr_002.passed is True
