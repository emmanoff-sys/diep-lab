"""Operational intelligence models for WP-010.

Frozen dataclasses only, mirroring the WP-007/WP-008/WP-009 layer
conventions: deterministic construction, no wall-clock or randomness —
identifiers derive from content and timestamps are supplied by callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from services.adms_operations import RestorationCandidate, SwitchingPlan, SwitchingStep

ScenarioActionKind = Literal["open_switch", "close_switch", "fail_edge", "fail_source"]
ContingencyElementKind = Literal["edge", "source"]
RuleCategory = Literal["safety", "validation", "engineering", "recommendation"]


class OperationalIntelligenceError(ValueError):
    """Raised when an intelligence request cannot be evaluated deterministically."""


@dataclass(frozen=True)
class FeederLoading:
    """Load served by one source in a (possibly hypothetical) network state."""

    feeder_id: str
    served_load_kw: float
    served_customer_count: int


@dataclass(frozen=True)
class ScenarioAction:
    kind: ScenarioActionKind
    target_id: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    description: str
    actions: tuple[ScenarioAction, ...]


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    description: str
    energized_before: tuple[str, ...]
    energized_after: tuple[str, ...]
    de_energized_nodes: tuple[str, ...]
    re_energized_nodes: tuple[str, ...]
    lost_load_kw: float
    lost_customer_count: int
    restored_load_kw: float
    restored_customer_count: int
    feeder_loading: tuple[FeederLoading, ...]

    @property
    def net_customer_delta(self) -> int:
        return self.restored_customer_count - self.lost_customer_count


@dataclass(frozen=True)
class ScenarioComparison:
    comparison_id: str
    outcomes: tuple[ScenarioOutcome, ...]
    ranking: tuple[str, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class ContingencyOutcome:
    contingency_id: str
    element_id: str
    element_kind: ContingencyElementKind
    de_energized_nodes: tuple[str, ...]
    lost_load_kw: float
    lost_customer_count: int
    mitigation_tie_edges: tuple[str, ...]
    severity_rank: int

    @property
    def has_mitigation(self) -> bool:
        return bool(self.mitigation_tie_edges)


@dataclass(frozen=True)
class ResilienceAssessment:
    assessment_id: str
    contingency_count: int
    unmitigated_contingency_ids: tuple[str, ...]
    worst_contingency_id: str | None
    max_lost_customer_count: int
    max_lost_load_kw: float


@dataclass(frozen=True)
class HistoricalEvent:
    """Caller-supplied prior event used for rule-based correlation."""

    asset_id: str
    kind: str
    observed_at: str


@dataclass(frozen=True)
class FaultCandidate:
    edge_id: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FaultLocationReport:
    subject_id: str
    observed_nodes: tuple[str, ...]
    candidates: tuple[FaultCandidate, ...]
    correlated_sources: tuple[str, ...]
    impacted_feeders: tuple[str, ...]


@dataclass(frozen=True)
class OperationalRule:
    """A configurable, deterministic rule: named evaluator plus parameters."""

    rule_id: str
    category: RuleCategory
    description: str
    evaluator: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleOutcome:
    rule_id: str
    category: RuleCategory
    passed: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleEvaluationTrace:
    evaluation_id: str
    outcomes: tuple[RuleOutcome, ...]

    @property
    def passed(self) -> bool:
        return all(outcome.passed for outcome in self.outcomes)

    @property
    def failures(self) -> tuple[RuleOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if not outcome.passed)


@dataclass(frozen=True)
class RestorationStrategy:
    strategy_id: str
    candidate: RestorationCandidate
    isolation_plan: SwitchingPlan
    restoration_plan: SwitchingPlan
    sequence: tuple[SwitchingStep, ...]
    switch_operation_count: int
    feeder_loading_after: tuple[FeederLoading, ...]
    max_feeder_load_kw: float
    capacity_ok: bool
    safe: bool
    rank: int


@dataclass(frozen=True)
class DecisionExplanation:
    explanation_id: str
    subject_id: str
    decision_kind: str
    summary: str
    rationale: tuple[str, ...]
    rule_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class IntelligenceAssessment:
    assessment_id: str
    subject_id: str
    fault_report: FaultLocationReport
    strategies: tuple[RestorationStrategy, ...]
    rule_trace: RuleEvaluationTrace
    explanations: tuple[DecisionExplanation, ...]
