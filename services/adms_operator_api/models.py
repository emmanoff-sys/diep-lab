"""Operator API view models for WP-013-02.

Frozen dataclasses forming the stable v1 client contract. These are
pure view models composed from the WP-006..010 layers — no business
logic lives here, and nothing in this package can mutate platform
state. Deterministic construction throughout: no wall clock, no
randomness; identifiers and timestamps come from the underlying layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

API_VERSION = "v1"

HealthStatus = Literal["operational", "degraded"]
IndicatorSeverity = Literal["normal", "attention"]
AssetKind = Literal["node", "edge"]


class OperatorApiError(ValueError):
    """Raised when an operator request cannot be answered deterministically."""


class AuthenticationError(OperatorApiError):
    """Raised when a caller cannot be identified."""


class AuthorizationError(OperatorApiError):
    """Raised when an identified caller lacks the required role."""


class UnknownAssetError(OperatorApiError):
    """Raised when a requested asset does not exist in the network model."""


@dataclass(frozen=True)
class OperatorPrincipal:
    operator_id: str
    display_name: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class ServiceHealth:
    name: str
    status: HealthStatus
    detail: str


@dataclass(frozen=True)
class PlatformStatus:
    node_count: int
    edge_count: int
    energized_node_count: int
    feeder_count: int
    active_outage_groups: int
    customers_affected: int


@dataclass(frozen=True)
class OperationalIndicator:
    indicator_id: str
    label: str
    value: str
    severity: IndicatorSeverity


@dataclass(frozen=True)
class OutageOverview:
    group_id: str
    feeder_ids: tuple[str, ...]
    affected_nodes: tuple[str, ...]
    customer_count: int
    candidate_cause_edges: tuple[str, ...]


@dataclass(frozen=True)
class DashboardView:
    platform: PlatformStatus
    services: tuple[ServiceHealth, ...]
    active_outages: tuple[OutageOverview, ...]
    indicators: tuple[OperationalIndicator, ...]


@dataclass(frozen=True)
class NodeView:
    node_id: str
    node_type: str
    name: str
    energized: bool
    available: bool


@dataclass(frozen=True)
class EdgeView:
    edge_id: str
    edge_type: str
    from_node: str
    to_node: str
    switchable: bool
    closed: bool
    available: bool


@dataclass(frozen=True)
class FeederStatusView:
    feeder_id: str
    healthy: bool
    energized_node_count: int
    deenergized_node_count: int
    fully_energized: bool


@dataclass(frozen=True)
class NetworkWorkspaceView:
    feeders: tuple[FeederStatusView, ...]
    nodes: tuple[NodeView, ...]
    edges: tuple[EdgeView, ...]


@dataclass(frozen=True)
class AssetSearchResult:
    asset_id: str
    kind: AssetKind
    label: str


@dataclass(frozen=True)
class AssetStatePanel:
    asset_id: str
    asset_kind: AssetKind
    available: bool
    closed: bool | None
    energized: bool | None
    history_count: int
    last_observed_at: str | None


@dataclass(frozen=True)
class TopologyNeighborhood:
    node_id: str
    node: NodeView
    edges: tuple[EdgeView, ...]
    neighbors: tuple[NodeView, ...]


@dataclass(frozen=True)
class RecommendationStepView:
    step_number: int
    action: str
    edge_id: str
    purpose: str


@dataclass(frozen=True)
class StrategyView:
    strategy_id: str
    rank: int
    safe: bool
    capacity_ok: bool
    tie_edge_id: str
    supply_feeder_id: str
    restored_customer_count: int
    restored_load_kw: float
    max_feeder_load_kw: float
    sequence: tuple[RecommendationStepView, ...]


@dataclass(frozen=True)
class ExplanationView:
    subject_id: str
    decision_kind: str
    summary: str
    rationale: tuple[str, ...]
    rule_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class RuleOutcomeView:
    rule_id: str
    category: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FaultCandidateView:
    edge_id: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationWorkspaceView:
    group_id: str
    outage: OutageOverview
    fault_candidates: tuple[FaultCandidateView, ...]
    strategies: tuple[StrategyView, ...]
    explanations: tuple[ExplanationView, ...]
    rule_outcomes: tuple[RuleOutcomeView, ...]


@dataclass(frozen=True)
class AuditRecordView:
    record_id: str
    sequence: int
    recorded_at: str
    kind: str
    subject_id: str
    actor: str
    related_record_ids: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class TimelineEntryView:
    occurred_at: str
    source: Literal["audit", "state"]
    reference_id: str
    description: str


@dataclass(frozen=True)
class HistoryWorkspaceView:
    records: tuple[AuditRecordView, ...]
    record_count: int
