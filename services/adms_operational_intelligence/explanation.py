"""OA-049 — decision explanation services.

Every WP-010 recommendation can be explained: what is recommended, which
rules were evaluated (with their ids for traceability), what evidence
supports it, and which constraints bind it. Explanations are plain
strings assembled deterministically from the underlying dataclasses.
"""

from __future__ import annotations

from .models import (
    ContingencyOutcome,
    DecisionExplanation,
    FaultLocationReport,
    RestorationStrategy,
    RuleEvaluationTrace,
)


class DecisionExplanationService:
    def explain_strategy(
        self,
        strategy: RestorationStrategy,
        *,
        rule_trace: RuleEvaluationTrace | None = None,
    ) -> DecisionExplanation:
        candidate = strategy.candidate
        rationale = [
            f"restores {len(candidate.restored_nodes)} node(s), "
            f"{candidate.restored_load_kw} kW and "
            f"{candidate.restored_customer_count} customer(s) "
            f"via tie {candidate.tie_edge_id} from feeder {candidate.supply_feeder_id}",
            f"requires {strategy.switch_operation_count} switch operation(s); "
            "isolation precedes restoration (SR-005)",
            f"post-restoration maximum feeder load is {strategy.max_feeder_load_kw} kW",
        ]
        constraints = []
        if candidate.path_capacity_kw is not None:
            constraints.append(
                f"path capacity {candidate.path_capacity_kw} kW limits restorable load"
            )
        if not strategy.capacity_ok:
            constraints.append(
                f"restored load {candidate.restored_load_kw} kW exceeds path capacity"
            )
        if not strategy.safe:
            failed = ", ".join(
                sorted(
                    {
                        result.rule_id
                        for plan in (strategy.isolation_plan, strategy.restoration_plan)
                        for result in plan.safety.failures
                    }
                )
            )
            constraints.append(f"switching safety rules failed: {failed}")

        evidence = [
            f"supply path: {' -> '.join(candidate.supply_path_nodes)}",
            f"restored nodes: {', '.join(candidate.restored_nodes)}",
        ]
        rule_ids: tuple[str, ...] = ()
        if rule_trace is not None:
            rule_ids = tuple(outcome.rule_id for outcome in rule_trace.outcomes)
            evidence.extend(
                f"rule {outcome.rule_id} "
                f"{'passed' if outcome.passed else 'FAILED'}: {outcome.detail}"
                for outcome in rule_trace.outcomes
            )

        verdict = "recommended" if strategy.safe and strategy.capacity_ok else "not recommended"
        return DecisionExplanation(
            explanation_id=f"explanation:{strategy.strategy_id}",
            subject_id=strategy.strategy_id,
            decision_kind="restoration_strategy",
            summary=(
                f"strategy {strategy.strategy_id} (rank {strategy.rank}) is {verdict}: "
                f"close {candidate.tie_edge_id} to resupply from {candidate.supply_feeder_id}"
            ),
            rationale=tuple(rationale),
            rule_ids=rule_ids,
            evidence=tuple(evidence),
            constraints=tuple(constraints),
        )

    def explain_contingency(self, outcome: ContingencyOutcome) -> DecisionExplanation:
        mitigation = (
            "candidate mitigation tie(s): " + ", ".join(outcome.mitigation_tie_edges)
            if outcome.has_mitigation
            else "no candidate mitigation exists; loss would be unrecoverable by switching"
        )
        return DecisionExplanation(
            explanation_id=f"explanation:{outcome.contingency_id}",
            subject_id=outcome.contingency_id,
            decision_kind="contingency",
            summary=(
                f"loss of {outcome.element_kind} {outcome.element_id} de-energises "
                f"{len(outcome.de_energized_nodes)} node(s) "
                f"({outcome.lost_customer_count} customer(s), {outcome.lost_load_kw} kW); "
                f"severity rank {outcome.severity_rank}"
            ),
            rationale=(mitigation,),
            rule_ids=(),
            evidence=(f"de-energised nodes: {', '.join(outcome.de_energized_nodes) or 'none'}",),
            constraints=(),
        )

    def explain_fault_report(self, report: FaultLocationReport) -> DecisionExplanation:
        if report.candidates:
            top = report.candidates[0]
            summary = (
                f"most probable fault segment for {report.subject_id} is {top.edge_id} "
                f"(confidence {top.confidence})"
            )
            evidence = top.evidence
        else:
            summary = f"no candidate fault segment identified for {report.subject_id}"
            evidence = ()
        return DecisionExplanation(
            explanation_id=f"explanation:fault:{report.subject_id}",
            subject_id=report.subject_id,
            decision_kind="fault_location",
            summary=summary,
            rationale=tuple(
                f"{candidate.edge_id}: confidence {candidate.confidence}"
                for candidate in report.candidates
            ),
            rule_ids=(),
            evidence=evidence,
            constraints=(),
        )
