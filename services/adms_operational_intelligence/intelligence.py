"""OA-051 — operational intelligence facade.

Composes the WP-010 analytical services over a detected WP-009 outage
group into one traceable, explainable assessment. Advisory only: the
assessment is data for the operator; nothing here executes control.
"""

from __future__ import annotations

from services.adms_operations import (
    IsolationBoundaryService,
    OperationalNetworkView,
    OutageGroup,
)

from .explanation import DecisionExplanationService
from .fault_location import FaultLocationAssistanceService
from .models import (
    DecisionExplanation,
    HistoricalEvent,
    IntelligenceAssessment,
    OperationalRule,
    RestorationStrategy,
    RuleEvaluationTrace,
)
from .restoration_optimizer import RestorationOptimisationService
from .rules import RuleEngine, default_operational_rules


class OperationalIntelligenceService:
    def __init__(
        self,
        view: OperationalNetworkView,
        *,
        rules: tuple[OperationalRule, ...] | None = None,
        history: tuple[HistoricalEvent, ...] = (),
    ) -> None:
        self.view = view
        self._isolation = IsolationBoundaryService(view)
        self._fault_location = FaultLocationAssistanceService(view, history=history)
        self._optimizer = RestorationOptimisationService(view)
        self._engine = RuleEngine(rules if rules is not None else default_operational_rules())
        self._explainer = DecisionExplanationService()

    def assess(self, group: OutageGroup) -> IntelligenceAssessment:
        """Full analytical assessment of a detected outage group."""
        boundary = self._isolation.analyze(group.group_id, group.affected_nodes)
        fault_report = self._fault_location.analyze(group.group_id, group.affected_nodes)
        strategies = self._optimizer.strategies(group.affected_nodes, boundary)

        explanations: list[DecisionExplanation] = [
            self._explainer.explain_fault_report(fault_report)
        ]
        rule_trace = self._empty_trace(group.group_id)
        for strategy in strategies:
            trace = self._evaluate_rules(strategy, boundary_verified=boundary.verified)
            if strategy.rank == 1:
                rule_trace = trace
            explanations.append(self._explainer.explain_strategy(strategy, rule_trace=trace))
        if not strategies:
            explanations.append(
                DecisionExplanation(
                    explanation_id=f"explanation:no-strategy:{group.group_id}",
                    subject_id=group.group_id,
                    decision_kind="restoration_strategy",
                    summary=(
                        f"no restoration strategy is currently available for {group.group_id}"
                    ),
                    rationale=(
                        "no open, operable tie connects the de-energised region "
                        "to a healthy feeder",
                    ),
                    rule_ids=(),
                    evidence=(),
                    constraints=(),
                )
            )

        return IntelligenceAssessment(
            assessment_id=f"assessment:{group.group_id}",
            subject_id=group.group_id,
            fault_report=fault_report,
            strategies=strategies,
            rule_trace=rule_trace,
            explanations=tuple(explanations),
        )

    def _evaluate_rules(
        self, strategy: RestorationStrategy, *, boundary_verified: bool
    ) -> RuleEvaluationTrace:
        failed_safety = tuple(
            sorted(
                {
                    result.rule_id
                    for plan in (strategy.isolation_plan, strategy.restoration_plan)
                    for result in plan.safety.failures
                }
            )
        )
        context = {
            "plan_safe": strategy.safe,
            "failed_safety_rules": failed_safety,
            "boundary_verified": boundary_verified,
            "load_kw": strategy.candidate.restored_load_kw,
            "capacity_kw": strategy.candidate.path_capacity_kw,
            "max_feeder_load_kw": strategy.max_feeder_load_kw,
        }
        return self._engine.evaluate(strategy.strategy_id, context)

    def _empty_trace(self, subject_id: str) -> RuleEvaluationTrace:
        return RuleEvaluationTrace(
            evaluation_id=f"rule-evaluation:{subject_id}",
            outcomes=(),
        )
