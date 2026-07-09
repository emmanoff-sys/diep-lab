"""OA-047 — rule-based restoration optimisation.

Builds complete restoration strategies from the WP-009 isolation,
restoration, and switching services, then ranks them deterministically:
safe first, capacity-satisfying first, most customers restored, best
feeder balance (lowest post-restoration maximum feeder load), fewest
switch operations, then strategy id. Rule-based only — power flow and
optimal switching are explicitly out of WP-010 scope.
"""

from __future__ import annotations

from dataclasses import replace

from services.adms_operations import (
    IsolationBoundary,
    OperationalNetworkView,
    RestorationCandidateService,
    SwitchingPlanService,
    SwitchingStep,
)

from .models import RestorationStrategy
from .overlay import HypotheticalNetworkState


class RestorationOptimisationService:
    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view
        self._restoration = RestorationCandidateService(view)
        self._switching = SwitchingPlanService(view)

    def strategies(
        self,
        affected_nodes: tuple[str, ...],
        boundary: IsolationBoundary,
    ) -> tuple[RestorationStrategy, ...]:
        """Ranked restoration strategies for an isolated region."""
        unranked: list[RestorationStrategy] = []
        for candidate in self._restoration.candidates(affected_nodes, boundary):
            isolation_plan = self._switching.build_isolation_plan(boundary)
            restoration_plan = self._switching.build_restoration_plan(candidate, boundary)
            sequence = self._sequence(isolation_plan.steps, restoration_plan.steps)
            loading = self._post_restoration_loading(boundary, candidate.tie_edge_id)
            unranked.append(
                RestorationStrategy(
                    strategy_id=f"strategy:{candidate.candidate_id}",
                    candidate=candidate,
                    isolation_plan=isolation_plan,
                    restoration_plan=restoration_plan,
                    sequence=sequence,
                    switch_operation_count=len(sequence),
                    feeder_loading_after=loading,
                    max_feeder_load_kw=max(
                        (feeder.served_load_kw for feeder in loading), default=0.0
                    ),
                    capacity_ok=candidate.capacity_ok,
                    safe=isolation_plan.safe and restoration_plan.safe,
                    rank=0,
                )
            )
        return self._rank(unranked)

    @staticmethod
    def _sequence(
        isolation_steps: tuple[SwitchingStep, ...],
        restoration_steps: tuple[SwitchingStep, ...],
    ) -> tuple[SwitchingStep, ...]:
        """Optimised operating sequence: isolation strictly before
        restoration (SR-005), renumbered as one contiguous plan."""
        combined = list(isolation_steps) + list(restoration_steps)
        return tuple(
            replace(step, step_number=index) for index, step in enumerate(combined, start=1)
        )

    def _post_restoration_loading(self, boundary: IsolationBoundary, tie_edge_id: str):
        """Feeder loading after executing the strategy: isolation points
        opened (except the tie being closed), the tie closed."""
        opened = frozenset(set(boundary.safe_isolation_edges) - {tie_edge_id})
        overlay = HypotheticalNetworkState(
            self.view,
            opened_edges=opened,
            closed_edges=frozenset({tie_edge_id}),
        )
        return overlay.feeder_loading()

    @staticmethod
    def _rank(unranked: list[RestorationStrategy]) -> tuple[RestorationStrategy, ...]:
        ordered = sorted(
            unranked,
            key=lambda strategy: (
                not strategy.safe,
                not strategy.capacity_ok,
                -strategy.candidate.restored_customer_count,
                strategy.max_feeder_load_kw,
                strategy.switch_operation_count,
                strategy.strategy_id,
            ),
        )
        return tuple(
            replace(strategy, rank=position) for position, strategy in enumerate(ordered, start=1)
        )
