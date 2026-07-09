"""OA-046 — rule-based fault location assistance.

Given an observed de-energised region, scores candidate fault segments
with additive, rule-based evidence. Confidence is NOT a probability —
it is a deterministic 0..1 score assembled from named evidence rules so
operators (and tests) can trace exactly why a segment ranks where it
does. State estimation and impedance-based fault location are explicitly
out of WP-010 scope.
"""

from __future__ import annotations

from services.adms_operations import OperationalNetworkView

from .models import FaultCandidate, FaultLocationReport, HistoricalEvent
from .overlay import HypotheticalNetworkState

_TOUCHES_REGION = 0.2
_ABNORMALLY_OPEN = 0.25
_UNAVAILABLE = 0.2
_EXPLAINS_EXACTLY = 0.25
_EXPLAINS_PARTIALLY = 0.1
_HISTORICAL_MATCH = 0.1


class FaultLocationAssistanceService:
    def __init__(
        self,
        view: OperationalNetworkView,
        *,
        history: tuple[HistoricalEvent, ...] = (),
    ) -> None:
        self.view = view
        self.history = history

    def analyze(self, subject_id: str, observed_nodes: tuple[str, ...]) -> FaultLocationReport:
        region = set(observed_nodes)
        candidates = tuple(
            sorted(
                (
                    candidate
                    for candidate in (
                        self._score(edge, region)
                        for edge in self.view.topology.edges
                        if {edge.from_node, edge.to_node} & region
                    )
                ),
                key=lambda candidate: (-candidate.confidence, candidate.edge_id),
            )
        )
        return FaultLocationReport(
            subject_id=subject_id,
            observed_nodes=tuple(sorted(region)),
            candidates=candidates,
            correlated_sources=self._correlated_sources(region),
            impacted_feeders=self._impacted_feeders(region),
        )

    def _score(self, edge, region: set[str]) -> FaultCandidate:
        confidence = _TOUCHES_REGION
        evidence = [f"edge {edge.edge_id} adjoins the de-energised region"]

        connectivity = self.view.operational_state.connectivity_state(edge.edge_id)
        if edge.normally_closed and not (connectivity.closed and connectivity.available):
            confidence += _ABNORMALLY_OPEN
            evidence.append(f"edge {edge.edge_id} is abnormally non-conducting in live state")
        if not connectivity.available:
            confidence += _UNAVAILABLE
            evidence.append(f"edge {edge.edge_id} is reported unavailable (fault indication)")

        explained = self._explained_dark_set(edge.edge_id)
        if explained == region:
            confidence += _EXPLAINS_EXACTLY
            evidence.append(
                f"sole failure of {edge.edge_id} in the normal network "
                "explains the observed outage exactly"
            )
        elif explained & region:
            confidence += _EXPLAINS_PARTIALLY
            evidence.append(
                f"sole failure of {edge.edge_id} in the normal network "
                "explains part of the observed outage"
            )

        events = sorted(
            event.observed_at for event in self.history if event.asset_id == edge.edge_id
        )
        if events:
            confidence += _HISTORICAL_MATCH
            evidence.append(
                f"historical events recorded for {edge.edge_id}: {len(events)} "
                f"(latest {events[-1]})"
            )

        return FaultCandidate(
            edge_id=edge.edge_id,
            confidence=round(min(confidence, 1.0), 4),
            evidence=tuple(evidence),
        )

    def _explained_dark_set(self, edge_id: str) -> set[str]:
        """Nodes that would be dark if ONLY this edge failed, from the
        as-designed (normal) network configuration."""
        overlay = HypotheticalNetworkState(
            self.view, base="normal", failed_edges=frozenset({edge_id})
        )
        all_nodes = {node.node_id for node in self.view.topology.nodes}
        return all_nodes - set(overlay.energized_nodes())

    def _correlated_sources(self, region: set[str]) -> tuple[str, ...]:
        return tuple(
            source_id
            for source_id in self.view.source_nodes()
            if not self.view.source_healthy(source_id)
            and set(self.view.normal_supply_extent(source_id)) & region
        )

    def _impacted_feeders(self, region: set[str]) -> tuple[str, ...]:
        return tuple(
            source_id
            for source_id in self.view.source_nodes()
            if set(self.view.normal_supply_extent(source_id)) & region
        )
