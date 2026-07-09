"""OA-039 — safe, non-destructive switching plan generation."""

from __future__ import annotations

from .models import (
    IsolationBoundary,
    PreconditionResult,
    RestorationCandidate,
    SafetyEvaluation,
    SafetyRuleResult,
    SwitchingPlan,
    SwitchingStep,
)
from .state_view import OperationalNetworkView


class SwitchingPlanService:
    """Generates ordered, rule-checked switching plans. Plans are data —
    nothing here executes a switch (automatic execution is explicitly out
    of WP-009 scope)."""

    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view

    def build_isolation_plan(self, boundary: IsolationBoundary) -> SwitchingPlan:
        steps: list[SwitchingStep] = []
        diagnostics: list[str] = []
        step_number = 0
        for point in boundary.isolation_points:
            if point.edge_id not in boundary.safe_isolation_edges:
                continue
            if not point.closed:
                diagnostics.append(
                    f"isolation point {point.edge_id} is already open; no step emitted"
                )
                continue
            step_number += 1
            steps.append(
                SwitchingStep(
                    step_number=step_number,
                    action="open",
                    edge_id=point.edge_id,
                    purpose="isolate",
                    expected_state_before="closed",
                    preconditions=(
                        f"device {point.edge_id} reported available",
                        f"device {point.edge_id} currently closed",
                    ),
                )
            )

        rollback = tuple(
            SwitchingStep(
                step_number=index,
                action="close",
                edge_id=step.edge_id,
                purpose="isolate",
                expected_state_before="open",
                preconditions=(f"device {step.edge_id} reported available",),
            )
            for index, step in enumerate(reversed(steps), start=1)
        )

        plan = SwitchingPlan(
            plan_id=f"plan:isolate:{boundary.subject_id}",
            objective="isolate outage region",
            subject_id=boundary.subject_id,
            steps=tuple(steps),
            rollback_steps=rollback,
            safety=self._evaluate_safety(tuple(steps), boundary, restoration=None),
            diagnostics=tuple(diagnostics),
        )
        return plan

    def build_restoration_plan(
        self,
        candidate: RestorationCandidate,
        boundary: IsolationBoundary,
    ) -> SwitchingPlan:
        tie_state = self.view.operational_state.connectivity_state(candidate.tie_edge_id)
        step = SwitchingStep(
            step_number=1,
            action="close",
            edge_id=candidate.tie_edge_id,
            purpose="restore",
            expected_state_before="open",
            preconditions=(
                f"isolation boundary for {boundary.subject_id} verified",
                f"device {candidate.tie_edge_id} reported available",
                f"device {candidate.tie_edge_id} currently open",
                "restored region de-energised before close",
            ),
        )
        diagnostics: list[str] = []
        if tie_state.closed:
            diagnostics.append(
                f"tie {candidate.tie_edge_id} is already closed; restoration "
                "plan is not applicable in the current state"
            )
        rollback = (
            SwitchingStep(
                step_number=1,
                action="open",
                edge_id=candidate.tie_edge_id,
                purpose="restore",
                expected_state_before="closed",
                preconditions=(f"device {candidate.tie_edge_id} reported available",),
            ),
        )
        return SwitchingPlan(
            plan_id=f"plan:restore:{boundary.subject_id}:{candidate.tie_edge_id}",
            objective="restore supply via alternative path",
            subject_id=boundary.subject_id,
            steps=(step,),
            rollback_steps=rollback,
            safety=self._evaluate_safety((step,), boundary, restoration=candidate),
            diagnostics=tuple(diagnostics),
        )

    def validate_preconditions(self, plan: SwitchingPlan) -> tuple[PreconditionResult, ...]:
        """Check each step's expected device state against live state."""
        results: list[PreconditionResult] = []
        for step in plan.steps:
            connectivity = self.view.operational_state.connectivity_state(step.edge_id)
            if not connectivity.available:
                results.append(
                    PreconditionResult(
                        step_number=step.step_number,
                        satisfied=False,
                        detail=f"device {step.edge_id} unavailable",
                    )
                )
                continue
            actual = "closed" if connectivity.closed else "open"
            if actual != step.expected_state_before:
                results.append(
                    PreconditionResult(
                        step_number=step.step_number,
                        satisfied=False,
                        detail=(
                            f"device {step.edge_id} expected "
                            f"{step.expected_state_before} but is {actual}"
                        ),
                    )
                )
                continue
            results.append(
                PreconditionResult(
                    step_number=step.step_number,
                    satisfied=True,
                    detail=f"device {step.edge_id} ready ({actual})",
                )
            )
        return tuple(results)

    def _evaluate_safety(
        self,
        steps: tuple[SwitchingStep, ...],
        boundary: IsolationBoundary,
        restoration: RestorationCandidate | None,
    ) -> SafetyEvaluation:
        results: list[SafetyRuleResult] = []
        switchable = {edge.edge_id: edge.is_switchable for edge in self.view.topology.edges}

        unavailable = tuple(
            step.edge_id
            for step in steps
            if not self.view.operational_state.connectivity_state(step.edge_id).available
        )
        results.append(
            SafetyRuleResult(
                rule_id="SR-001",
                description="no step operates an unavailable device",
                passed=not unavailable,
                detail="all devices available" if not unavailable else ", ".join(unavailable),
            )
        )

        non_switchable = tuple(
            step.edge_id for step in steps if not switchable.get(step.edge_id, False)
        )
        results.append(
            SafetyRuleResult(
                rule_id="SR-002",
                description="only switchable devices are operated",
                passed=not non_switchable,
                detail=(
                    "all operated devices switchable"
                    if not non_switchable
                    else ", ".join(non_switchable)
                ),
            )
        )

        closes = tuple(step for step in steps if step.action == "close")
        close_without_isolation = bool(closes) and not boundary.verified
        results.append(
            SafetyRuleResult(
                rule_id="SR-003",
                description="no close operation before the fault region is isolated",
                passed=not close_without_isolation,
                detail=(
                    "isolation verified before any close"
                    if not close_without_isolation
                    else f"boundary for {boundary.subject_id} is not verified"
                ),
            )
        )

        parallel_feed = False
        parallel_detail = "no energised-to-energised close"
        if restoration is not None:
            energized = set(
                self.view.energized_nodes(blocked_edges=frozenset(boundary.safe_isolation_edges))
            )
            restored = set(restoration.restored_nodes)
            if restored & energized:
                parallel_feed = True
                parallel_detail = "restoration target already energised: " + ", ".join(
                    sorted(restored & energized)
                )
        results.append(
            SafetyRuleResult(
                rule_id="SR-004",
                description="closing must not create a parallel feed",
                passed=not parallel_feed,
                detail=parallel_detail,
            )
        )

        ordered = all(steps[index].step_number == index + 1 for index in range(len(steps))) and all(
            steps[index].purpose != "restore" or steps[jndex].purpose != "isolate"
            for index in range(len(steps))
            for jndex in range(index + 1, len(steps))
        )
        results.append(
            SafetyRuleResult(
                rule_id="SR-005",
                description="steps are strictly ordered; isolation precedes restoration",
                passed=ordered,
                detail="ordering valid" if ordered else "step ordering violation",
            )
        )

        return SafetyEvaluation(results=tuple(results))
