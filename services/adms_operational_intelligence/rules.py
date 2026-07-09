"""OA-048 — deterministic operational rule engine.

Rules are data (`OperationalRule`): a named evaluator plus parameters.
Evaluators are pure functions of (parameters, context) registered by
name, so rule sets are configurable without code changes and every
evaluation is traceable — each outcome records the exact inputs it used.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .models import (
    OperationalIntelligenceError,
    OperationalRule,
    RuleEvaluationTrace,
    RuleOutcome,
)

Evaluator = Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[bool, str, dict[str, Any]]]


def _require(context: Mapping[str, Any], key: str, rule_id: str) -> Any:
    if key not in context:
        raise OperationalIntelligenceError(f"rule {rule_id}: context is missing '{key}'")
    return context[key]


def _evaluate_capacity_margin(
    parameters: Mapping[str, Any], context: Mapping[str, Any]
) -> tuple[bool, str, dict[str, Any]]:
    margin = float(parameters.get("margin_fraction", 0.0))
    load_kw = float(_require(context, "load_kw", "capacity_margin"))
    capacity_kw = context.get("capacity_kw")
    if capacity_kw is None:
        return True, "no path rating available; capacity rule not binding", {"load_kw": load_kw}
    limit = float(capacity_kw) * (1.0 - margin)
    passed = load_kw <= limit
    detail = (
        f"load {load_kw} kW within capacity limit {limit} kW"
        if passed
        else f"load {load_kw} kW exceeds capacity limit {limit} kW"
    )
    return passed, detail, {"load_kw": load_kw, "capacity_kw": float(capacity_kw), "limit": limit}


def _evaluate_boundary_verified(
    parameters: Mapping[str, Any], context: Mapping[str, Any]
) -> tuple[bool, str, dict[str, Any]]:
    verified = bool(_require(context, "boundary_verified", "boundary_verified"))
    detail = "isolation boundary verified" if verified else "isolation boundary NOT verified"
    return verified, detail, {"boundary_verified": verified}


def _evaluate_plan_safety(
    parameters: Mapping[str, Any], context: Mapping[str, Any]
) -> tuple[bool, str, dict[str, Any]]:
    safe = bool(_require(context, "plan_safe", "plan_safety"))
    failed = tuple(context.get("failed_safety_rules", ()))
    detail = (
        "switching plan passed all safety rules"
        if safe
        else "switching plan failed safety rules: " + ", ".join(failed)
    )
    return safe, detail, {"plan_safe": safe, "failed_safety_rules": list(failed)}


def _evaluate_feeder_load_limit(
    parameters: Mapping[str, Any], context: Mapping[str, Any]
) -> tuple[bool, str, dict[str, Any]]:
    limit = float(parameters.get("max_load_kw", float("inf")))
    max_load = float(_require(context, "max_feeder_load_kw", "feeder_load_limit"))
    passed = max_load <= limit
    detail = (
        f"maximum feeder load {max_load} kW within limit {limit} kW"
        if passed
        else f"maximum feeder load {max_load} kW exceeds limit {limit} kW"
    )
    return passed, detail, {"max_feeder_load_kw": max_load, "max_load_kw": limit}


_BUILTIN_EVALUATORS: dict[str, Evaluator] = {
    "capacity_margin": _evaluate_capacity_margin,
    "boundary_verified": _evaluate_boundary_verified,
    "plan_safety": _evaluate_plan_safety,
    "feeder_load_limit": _evaluate_feeder_load_limit,
}


def default_operational_rules() -> tuple[OperationalRule, ...]:
    """The standard WP-010 rule set used to gate recommendations."""
    return (
        OperationalRule(
            rule_id="OI-R-001",
            category="safety",
            description="recommended switching plan must pass WP-009 safety rules",
            evaluator="plan_safety",
        ),
        OperationalRule(
            rule_id="OI-R-002",
            category="validation",
            description="isolation boundary must be verified before restoration",
            evaluator="boundary_verified",
        ),
        OperationalRule(
            rule_id="OI-R-003",
            category="engineering",
            description="restored load must respect path capacity",
            evaluator="capacity_margin",
            parameters={"margin_fraction": 0.0},
        ),
        OperationalRule(
            rule_id="OI-R-004",
            category="recommendation",
            description="post-restoration feeder loading must stay within limit",
            evaluator="feeder_load_limit",
            parameters={"max_load_kw": 1000.0},
        ),
    )


class RuleEngine:
    def __init__(
        self,
        rules: tuple[OperationalRule, ...],
        *,
        evaluators: Mapping[str, Evaluator] | None = None,
    ) -> None:
        self.rules = rules
        self.evaluators: dict[str, Evaluator] = dict(_BUILTIN_EVALUATORS)
        if evaluators:
            self.evaluators.update(evaluators)
        for rule in rules:
            if rule.evaluator not in self.evaluators:
                raise OperationalIntelligenceError(
                    f"rule {rule.rule_id} references unknown evaluator '{rule.evaluator}'"
                )

    def evaluate(self, subject_id: str, context: Mapping[str, Any]) -> RuleEvaluationTrace:
        """Evaluate every rule in definition order against `context`."""
        outcomes: list[RuleOutcome] = []
        for rule in self.rules:
            passed, detail, evidence = self.evaluators[rule.evaluator](rule.parameters, context)
            outcomes.append(
                RuleOutcome(
                    rule_id=rule.rule_id,
                    category=rule.category,
                    passed=passed,
                    detail=detail,
                    evidence=evidence,
                )
            )
        return RuleEvaluationTrace(
            evaluation_id=f"rule-evaluation:{subject_id}",
            outcomes=tuple(outcomes),
        )
