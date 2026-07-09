"""OA-045 — deterministic N-1 contingency analysis.

Evaluates hypothetical single-element failures (conducting edges and
healthy sources) against the live operational baseline, ranks impacts,
and identifies candidate mitigations (open, operable tie switches that
bridge the lost region back to the live network). Analysis only — no
state changes and no switching execution.
"""

from __future__ import annotations

from services.adms_operations import OperationalNetworkView

from .models import ContingencyElementKind, ContingencyOutcome, ResilienceAssessment
from .overlay import HypotheticalNetworkState


class ContingencyAnalysisService:
    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view

    def evaluate_n1(self) -> tuple[ContingencyOutcome, ...]:
        """All single-element contingencies, ranked most severe first."""
        unranked: list[ContingencyOutcome] = []
        for edge in sorted(self.view.topology.edges, key=lambda item: item.edge_id):
            if not self.view.edge_conducting(edge.edge_id):
                continue
            unranked.append(self._evaluate(edge.edge_id, "edge"))
        for source_id in self.view.source_nodes():
            if self.view.source_healthy(source_id):
                unranked.append(self._evaluate(source_id, "source"))
        return self._rank(unranked)

    def evaluate_element(self, element_id: str, kind: ContingencyElementKind) -> ContingencyOutcome:
        """A single named contingency (rank 1 within its own report)."""
        return self._rank([self._evaluate(element_id, kind)])[0]

    def resilience_assessment(
        self, outcomes: tuple[ContingencyOutcome, ...]
    ) -> ResilienceAssessment:
        """Summary view: how exposed is the network to single failures?"""
        unmitigated = tuple(
            outcome.contingency_id
            for outcome in outcomes
            if outcome.de_energized_nodes and not outcome.has_mitigation
        )
        worst = outcomes[0] if outcomes else None
        return ResilienceAssessment(
            assessment_id="resilience:n-1",
            contingency_count=len(outcomes),
            unmitigated_contingency_ids=unmitigated,
            worst_contingency_id=worst.contingency_id if worst else None,
            max_lost_customer_count=worst.lost_customer_count if worst else 0,
            max_lost_load_kw=worst.lost_load_kw if worst else 0.0,
        )

    def _evaluate(self, element_id: str, kind: ContingencyElementKind) -> ContingencyOutcome:
        overlay = HypotheticalNetworkState(
            self.view,
            failed_edges=frozenset({element_id}) if kind == "edge" else frozenset(),
            failed_sources=frozenset({element_id}) if kind == "source" else frozenset(),
        )
        baseline = set(self.view.energized_nodes())
        after = set(overlay.energized_nodes())
        lost = tuple(sorted(baseline - after))
        return ContingencyOutcome(
            contingency_id=f"contingency:{kind}:{element_id}",
            element_id=element_id,
            element_kind=kind,
            de_energized_nodes=lost,
            lost_load_kw=sum(self.view.node_load_kw(node) for node in lost),
            lost_customer_count=sum(self.view.node_customer_count(node) for node in lost),
            mitigation_tie_edges=self._mitigations(set(lost), after),
            severity_rank=0,
        )

    def _mitigations(self, lost: set[str], energized_after: set[str]) -> tuple[str, ...]:
        """Open, operable switchable edges bridging the lost region back to
        the still-live network — candidate mitigation identification only;
        closing them is governed by the WP-009 switching safety rules."""
        ties: set[str] = set()
        for edge in self.view.topology.edges:
            if not edge.is_switchable:
                continue
            connectivity = self.view.operational_state.connectivity_state(edge.edge_id)
            if connectivity.closed or not connectivity.available:
                continue
            sides = {edge.from_node, edge.to_node}
            if sides & lost and sides & energized_after:
                ties.add(edge.edge_id)
        return tuple(sorted(ties))

    @staticmethod
    def _rank(outcomes: list[ContingencyOutcome]) -> tuple[ContingencyOutcome, ...]:
        ordered = sorted(
            outcomes,
            key=lambda outcome: (
                -outcome.lost_customer_count,
                -outcome.lost_load_kw,
                outcome.contingency_id,
            ),
        )
        return tuple(
            ContingencyOutcome(
                contingency_id=outcome.contingency_id,
                element_id=outcome.element_id,
                element_kind=outcome.element_kind,
                de_energized_nodes=outcome.de_energized_nodes,
                lost_load_kw=outcome.lost_load_kw,
                lost_customer_count=outcome.lost_customer_count,
                mitigation_tie_edges=outcome.mitigation_tie_edges,
                severity_rank=position,
            )
            for position, outcome in enumerate(ordered, start=1)
        )
