"""Operations and decision-support models for WP-009.

Frozen dataclasses only, mirroring the WP-007/WP-008 layer conventions:
deterministic construction, no wall-clock or randomness — identifiers derive
from content and timestamps are supplied by callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OutageKind = Literal["loss_of_supply", "source_loss", "feeder_outage"]
SwitchingAction = Literal["open", "close"]
StepPurpose = Literal["isolate", "restore"]
DecisionKind = Literal[
    "outage_detected",
    "plan_generated",
    "recommendation_issued",
    "operator_acknowledgement",
]


class OperationsError(ValueError):
    """Raised when an operations request cannot be evaluated deterministically."""


@dataclass(frozen=True)
class DetectedOutage:
    outage_id: str
    kind: OutageKind
    feeder_id: str
    affected_nodes: tuple[str, ...]
    candidate_cause_edges: tuple[str, ...]
    customer_count: int


@dataclass(frozen=True)
class OutageGroup:
    group_id: str
    outages: tuple[DetectedOutage, ...]
    affected_nodes: tuple[str, ...]
    feeder_ids: tuple[str, ...]
    customer_count: int


@dataclass(frozen=True)
class IsolationPoint:
    edge_id: str
    from_node: str
    to_node: str
    switchable: bool
    closed: bool
    available: bool

    @property
    def operable(self) -> bool:
        return self.switchable and self.available


@dataclass(frozen=True)
class IsolationBoundary:
    subject_id: str
    isolation_points: tuple[IsolationPoint, ...]
    safe_isolation_edges: tuple[str, ...]
    verified: bool
    unisolated_nodes: tuple[str, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class SafetyRuleResult:
    rule_id: str
    description: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class SafetyEvaluation:
    results: tuple[SafetyRuleResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failures(self) -> tuple[SafetyRuleResult, ...]:
        return tuple(result for result in self.results if not result.passed)


@dataclass(frozen=True)
class SwitchingStep:
    step_number: int
    action: SwitchingAction
    edge_id: str
    purpose: StepPurpose
    expected_state_before: Literal["open", "closed"]
    preconditions: tuple[str, ...]


@dataclass(frozen=True)
class PreconditionResult:
    step_number: int
    satisfied: bool
    detail: str


@dataclass(frozen=True)
class SwitchingPlan:
    plan_id: str
    objective: str
    subject_id: str
    steps: tuple[SwitchingStep, ...]
    rollback_steps: tuple[SwitchingStep, ...]
    safety: SafetyEvaluation
    diagnostics: tuple[str, ...]

    @property
    def safe(self) -> bool:
        return self.safety.passed


@dataclass(frozen=True)
class RestorationCandidate:
    candidate_id: str
    tie_edge_id: str
    supply_feeder_id: str
    supply_path_nodes: tuple[str, ...]
    restored_nodes: tuple[str, ...]
    restored_load_kw: float
    restored_customer_count: int
    path_capacity_kw: float | None
    capacity_ok: bool


@dataclass(frozen=True)
class SafetyAdvisory:
    advisory_id: str
    severity: Literal["info", "caution", "warning"]
    message: str


@dataclass(frozen=True)
class OutageSummary:
    subject_id: str
    kinds: tuple[OutageKind, ...]
    feeder_ids: tuple[str, ...]
    affected_node_count: int
    customer_count: int
    candidate_cause_edges: tuple[str, ...]


@dataclass(frozen=True)
class OperatorRecommendation:
    recommendation_id: str
    subject_id: str
    summary: OutageSummary
    isolation_plan: SwitchingPlan
    restoration_candidates: tuple[RestorationCandidate, ...]
    restoration_plans: tuple[SwitchingPlan, ...]
    advisories: tuple[SafetyAdvisory, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class DecisionRecord:
    record_id: str
    sequence: int
    recorded_at: str
    kind: DecisionKind
    subject_id: str
    actor: str
    related_record_ids: tuple[str, ...]
    payload: dict[str, Any] = field(default_factory=dict)
