"""Operator view composition for WP-013-02 (OA-061).

Aggregates the WP-007..010 layers into operator view models. This layer
only maps and composes — outage detection, isolation, switching safety,
restoration ranking, rule evaluation, and explanations all come from
the existing services unchanged (no business-logic duplication), and
every method is read-only.
"""

from __future__ import annotations

from services.adms_operational_intelligence import (
    ContingencyAnalysisService,
    HistoricalEvent,
    IntelligenceAssessment,
    OperationalIntelligenceService,
)
from services.adms_operational_state import InMemoryOperationalStateRepository
from services.adms_operations import (
    DecisionRecord,
    OperationalNetworkView,
    OperationsAuditTrail,
    OperationsError,
    OutageDetectionService,
    OutageGroup,
)

from .models import (
    AssetSearchResult,
    AssetStatePanel,
    AuditRecordView,
    DashboardView,
    EdgeView,
    ExplanationView,
    FaultCandidateView,
    FeederStatusView,
    HistoryWorkspaceView,
    NetworkWorkspaceView,
    NodeView,
    OperationalIndicator,
    OperatorApiError,
    OutageOverview,
    PlatformStatus,
    RecommendationStepView,
    RecommendationWorkspaceView,
    RuleOutcomeView,
    ServiceHealth,
    StrategyView,
    TimelineEntryView,
    TopologyNeighborhood,
    UnknownAssetError,
)


class OperatorViewService:
    def __init__(
        self,
        view: OperationalNetworkView,
        *,
        state_repository: InMemoryOperationalStateRepository | None = None,
        audit: OperationsAuditTrail | None = None,
        history: tuple[HistoricalEvent, ...] = (),
    ) -> None:
        self.view = view
        self.state_repository = state_repository
        self.audit = audit
        self._detection = OutageDetectionService(view)
        self._intelligence = OperationalIntelligenceService(view, history=history)
        self._contingency = ContingencyAnalysisService(view)

    # --- OA-063: situational awareness dashboard --------------------------------
    def dashboard(self) -> DashboardView:
        groups = self._detection.detect_all()
        energized = self.view.energized_nodes()
        customers_affected = sum(group.customer_count for group in groups)
        platform = PlatformStatus(
            node_count=len(self.view.topology.nodes),
            edge_count=len(self.view.topology.edges),
            energized_node_count=len(energized),
            feeder_count=len(self.view.source_nodes()),
            active_outage_groups=len(groups),
            customers_affected=customers_affected,
        )
        return DashboardView(
            platform=platform,
            services=self._service_health(),
            active_outages=tuple(self._outage_overview(group) for group in groups),
            indicators=self._indicators(platform),
        )

    def _service_health(self) -> tuple[ServiceHealth, ...]:
        checks = (
            ("topology-services", self._check_topology),
            ("operational-state", self._check_operational_state),
            ("outage-detection", self._check_detection),
            ("operational-intelligence", self._check_intelligence),
        )
        results = []
        for name, check in checks:
            try:
                detail = check()
                results.append(ServiceHealth(name=name, status="operational", detail=detail))
            except Exception as error:  # noqa: BLE001 - health must degrade, not raise
                results.append(ServiceHealth(name=name, status="degraded", detail=str(error)))
        return tuple(results)

    def _check_topology(self) -> str:
        nodes = len(self.view.topology.nodes)
        if nodes == 0:
            raise OperatorApiError("network model is empty")
        return f"network model loaded: {nodes} node(s), {len(self.view.topology.edges)} edge(s)"

    def _check_operational_state(self) -> str:
        states = self.view.operational_state.network_states()
        return f"live state responsive: {len(states)} tracked asset state(s)"

    def _check_detection(self) -> str:
        groups = self._detection.detect_all()
        return f"detection responsive: {len(groups)} active outage group(s)"

    def _check_intelligence(self) -> str:
        outcomes = self._contingency.evaluate_n1()
        return f"intelligence responsive: {len(outcomes)} N-1 contingencies evaluated"

    def _indicators(self, platform: PlatformStatus) -> tuple[OperationalIndicator, ...]:
        feeders = [self.view.source_healthy(feeder_id) for feeder_id in self.view.source_nodes()]
        healthy_feeders = sum(1 for healthy in feeders if healthy)
        outcomes = self._contingency.evaluate_n1()
        assessment = self._contingency.resilience_assessment(outcomes)
        unmitigated = len(assessment.unmitigated_contingency_ids)
        return (
            OperationalIndicator(
                indicator_id="customers-affected",
                label="Customers affected",
                value=str(platform.customers_affected),
                severity="attention" if platform.customers_affected else "normal",
            ),
            OperationalIndicator(
                indicator_id="energized-nodes",
                label="Energised nodes",
                value=f"{platform.energized_node_count}/{platform.node_count}",
                severity=(
                    "normal"
                    if platform.energized_node_count == platform.node_count
                    else "attention"
                ),
            ),
            OperationalIndicator(
                indicator_id="healthy-feeders",
                label="Healthy feeders",
                value=f"{healthy_feeders}/{len(feeders)}",
                severity="normal" if healthy_feeders == len(feeders) else "attention",
            ),
            OperationalIndicator(
                indicator_id="n1-unmitigated",
                label="Unmitigated N-1 contingencies",
                value=str(unmitigated),
                severity="attention" if unmitigated else "normal",
            ),
        )

    @staticmethod
    def _outage_overview(group: OutageGroup) -> OutageOverview:
        causes = tuple(
            sorted({edge for outage in group.outages for edge in outage.candidate_cause_edges})
        )
        return OutageOverview(
            group_id=group.group_id,
            feeder_ids=group.feeder_ids,
            affected_nodes=group.affected_nodes,
            customer_count=group.customer_count,
            candidate_cause_edges=causes,
        )

    # --- OA-064: network operations workspace ------------------------------------
    def network_workspace(self) -> NetworkWorkspaceView:
        energized = set(self.view.energized_nodes())
        feeders = []
        for feeder_id in self.view.source_nodes():
            # Status is judged over the feeder's NORMAL supply extent
            # (WP-009 semantics): an open tie to another feeder's dark
            # region must not mark this feeder as degraded.
            extent = set(self.view.normal_supply_extent(feeder_id))
            dark = extent - energized
            feeders.append(
                FeederStatusView(
                    feeder_id=feeder_id,
                    healthy=self.view.source_healthy(feeder_id),
                    energized_node_count=len(extent & energized),
                    deenergized_node_count=len(dark),
                    fully_energized=not dark,
                )
            )
        nodes = tuple(self._node_view(node.node_id, energized) for node in self.view.topology.nodes)
        edges = tuple(self._edge_view(edge.edge_id) for edge in self.view.topology.edges)
        return NetworkWorkspaceView(
            feeders=tuple(feeders),
            nodes=tuple(sorted(nodes, key=lambda item: item.node_id)),
            edges=tuple(sorted(edges, key=lambda item: item.edge_id)),
        )

    def _node_view(self, node_id: str, energized: set[str]) -> NodeView:
        node = self.view.topology.require_node(node_id)
        return NodeView(
            node_id=node.node_id,
            node_type=node.node_type,
            name=node.name or node.node_id,
            energized=node.node_id in energized,
            available=self.view.node_traversable(node.node_id),
        )

    def _edge_view(self, edge_id: str) -> EdgeView:
        edge = self.view.topology.require_edge(edge_id)
        connectivity = self.view.operational_state.connectivity_state(edge_id)
        return EdgeView(
            edge_id=edge.edge_id,
            edge_type=edge.edge_type,
            from_node=edge.from_node,
            to_node=edge.to_node,
            switchable=edge.is_switchable,
            closed=connectivity.closed,
            available=connectivity.available,
        )

    def asset_search(self, query: str) -> tuple[AssetSearchResult, ...]:
        needle = query.strip().lower()
        if not needle:
            return ()
        results: list[AssetSearchResult] = []
        for node in self.view.topology.nodes:
            haystack = f"{node.node_id} {node.name or ''} {node.node_type}".lower()
            if needle in haystack:
                results.append(
                    AssetSearchResult(
                        asset_id=node.node_id,
                        kind="node",
                        label=f"{node.node_type} {node.node_id}",
                    )
                )
        for edge in self.view.topology.edges:
            haystack = f"{edge.edge_id} {edge.edge_type} {edge.from_node} {edge.to_node}".lower()
            if needle in haystack:
                results.append(
                    AssetSearchResult(
                        asset_id=edge.edge_id,
                        kind="edge",
                        label=f"{edge.edge_type} {edge.edge_id} ({edge.from_node}-{edge.to_node})",
                    )
                )
        return tuple(sorted(results, key=lambda item: (item.kind, item.asset_id)))

    def asset_state_panel(self, asset_id: str) -> AssetStatePanel:
        kind = self._asset_kind(asset_id)
        if kind == "edge":
            connectivity = self.view.operational_state.connectivity_state(asset_id)
            available = connectivity.available
            closed: bool | None = connectivity.closed
            energized = connectivity.energized
        else:
            available = self.view.node_traversable(asset_id)
            closed = None
            energized = asset_id in set(self.view.energized_nodes())
        entries = (
            self.state_repository.history(asset_id) if self.state_repository is not None else ()
        )
        return AssetStatePanel(
            asset_id=asset_id,
            asset_kind=kind,
            available=available,
            closed=closed,
            energized=energized,
            history_count=len(entries),
            last_observed_at=entries[-1].update.observed_at if entries else None,
        )

    def topology_explorer(self, node_id: str) -> TopologyNeighborhood:
        if self._asset_kind(node_id) != "node":
            raise UnknownAssetError(f"unknown node: {node_id}")
        energized = set(self.view.energized_nodes())
        edges = tuple(
            sorted(
                (
                    self._edge_view(edge.edge_id)
                    for edge in self.view.topology.edges_for_node(node_id, include_open=True)
                ),
                key=lambda item: item.edge_id,
            )
        )
        neighbor_ids = sorted(
            {edge.from_node for edge in edges} | {edge.to_node for edge in edges} - {node_id}
        )
        neighbors = tuple(
            self._node_view(neighbor, energized) for neighbor in neighbor_ids if neighbor != node_id
        )
        return TopologyNeighborhood(
            node_id=node_id,
            node=self._node_view(node_id, energized),
            edges=edges,
            neighbors=neighbors,
        )

    def _asset_kind(self, asset_id: str) -> str:
        if any(node.node_id == asset_id for node in self.view.topology.nodes):
            return "node"
        if any(edge.edge_id == asset_id for edge in self.view.topology.edges):
            return "edge"
        raise UnknownAssetError(f"unknown asset: {asset_id}")

    # --- OA-065: operational recommendations workspace ---------------------------
    def recommendations(self) -> tuple[RecommendationWorkspaceView, ...]:
        return tuple(
            self._recommendation_view(group, self._intelligence.assess(group))
            for group in self._detection.detect_all()
        )

    def _recommendation_view(
        self, group: OutageGroup, assessment: IntelligenceAssessment
    ) -> RecommendationWorkspaceView:
        strategies = tuple(
            StrategyView(
                strategy_id=strategy.strategy_id,
                rank=strategy.rank,
                safe=strategy.safe,
                capacity_ok=strategy.capacity_ok,
                tie_edge_id=strategy.candidate.tie_edge_id,
                supply_feeder_id=strategy.candidate.supply_feeder_id,
                restored_customer_count=strategy.candidate.restored_customer_count,
                restored_load_kw=strategy.candidate.restored_load_kw,
                max_feeder_load_kw=strategy.max_feeder_load_kw,
                sequence=tuple(
                    RecommendationStepView(
                        step_number=step.step_number,
                        action=step.action,
                        edge_id=step.edge_id,
                        purpose=step.purpose,
                    )
                    for step in strategy.sequence
                ),
            )
            for strategy in assessment.strategies
        )
        explanations = tuple(
            ExplanationView(
                subject_id=explanation.subject_id,
                decision_kind=explanation.decision_kind,
                summary=explanation.summary,
                rationale=explanation.rationale,
                rule_ids=explanation.rule_ids,
                evidence=explanation.evidence,
                constraints=explanation.constraints,
            )
            for explanation in assessment.explanations
        )
        return RecommendationWorkspaceView(
            group_id=group.group_id,
            outage=self._outage_overview(group),
            fault_candidates=tuple(
                FaultCandidateView(
                    edge_id=candidate.edge_id,
                    confidence=candidate.confidence,
                    evidence=candidate.evidence,
                )
                for candidate in assessment.fault_report.candidates
            ),
            strategies=strategies,
            explanations=explanations,
            rule_outcomes=tuple(
                RuleOutcomeView(
                    rule_id=outcome.rule_id,
                    category=outcome.category,
                    passed=outcome.passed,
                    detail=outcome.detail,
                )
                for outcome in assessment.rule_trace.outcomes
            ),
        )

    # --- OA-066: operational history workspace -----------------------------------
    def audit_history(
        self,
        *,
        kind: str | None = None,
        subject_id: str | None = None,
        actor: str | None = None,
        text: str | None = None,
    ) -> HistoryWorkspaceView:
        records = self._audit_records(kind=kind, subject_id=subject_id)
        if actor is not None:
            records = tuple(record for record in records if record.actor == actor)
        if text:
            needle = text.strip().lower()
            records = tuple(record for record in records if needle in self._record_haystack(record))
        views = tuple(self._record_view(record) for record in records)
        return HistoryWorkspaceView(records=views, record_count=len(views))

    def recommendation_history(self) -> HistoryWorkspaceView:
        return self.audit_history(kind="recommendation_issued")

    def record_trace(self, record_id: str) -> tuple[AuditRecordView, ...]:
        if self.audit is None:
            raise OperatorApiError("audit trail is not configured for this workspace")
        try:
            records = self.audit.trace(record_id)
        except OperationsError as error:
            raise UnknownAssetError(str(error)) from error
        return tuple(self._record_view(record) for record in records)

    def timeline(self, asset_id: str | None = None) -> tuple[TimelineEntryView, ...]:
        entries: list[TimelineEntryView] = []
        for record in self._audit_records():
            if asset_id is not None and asset_id not in record.subject_id:
                continue
            entries.append(
                TimelineEntryView(
                    occurred_at=record.recorded_at,
                    source="audit",
                    reference_id=record.record_id,
                    description=f"{record.kind} for {record.subject_id} by {record.actor}",
                )
            )
        if self.state_repository is not None and asset_id is not None:
            for entry in self.state_repository.history(asset_id):
                entries.append(
                    TimelineEntryView(
                        occurred_at=entry.update.observed_at,
                        source="state",
                        reference_id=entry.update.update_id,
                        description=(
                            f"state update for {entry.update.asset_id} " f"by {entry.update.actor}"
                        ),
                    )
                )
        return tuple(
            sorted(entries, key=lambda item: (item.occurred_at, item.source, item.reference_id))
        )

    def _audit_records(
        self, *, kind: str | None = None, subject_id: str | None = None
    ) -> tuple[DecisionRecord, ...]:
        if self.audit is None:
            return ()
        return self.audit.history(kind=kind, subject_id=subject_id)

    @staticmethod
    def _record_haystack(record: DecisionRecord) -> str:
        payload_text = " ".join(f"{key}={value}" for key, value in sorted(record.payload.items()))
        return f"{record.record_id} {record.kind} {record.subject_id} {payload_text}".lower()

    @staticmethod
    def _record_view(record: DecisionRecord) -> AuditRecordView:
        note = record.payload.get("note")
        summary = str(note) if note else f"{record.kind.replace('_', ' ')} for {record.subject_id}"
        return AuditRecordView(
            record_id=record.record_id,
            sequence=record.sequence,
            recorded_at=record.recorded_at,
            kind=record.kind,
            subject_id=record.subject_id,
            actor=record.actor,
            related_record_ids=record.related_record_ids,
            summary=summary,
        )
