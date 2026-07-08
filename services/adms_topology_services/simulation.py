"""Non-destructive switching simulation services."""

from __future__ import annotations

from dataclasses import dataclass

from .graph import ConnectivityGraph
from .repository import InMemoryTopologyRepository, TopologyRepositoryError
from .tracing import SOURCE_NODE_TYPES


@dataclass(frozen=True)
class SwitchingSimulationResult:
    edge_id: str
    requested_closed: bool
    accepted: bool
    reason: str | None
    original_closed: bool
    affected_nodes: tuple[str, ...]
    repository: InMemoryTopologyRepository


class SwitchingSimulationService:
    def __init__(self, repository: InMemoryTopologyRepository) -> None:
        self.repository = repository
        self.graph = ConnectivityGraph(repository)

    def simulate_switch(
        self,
        edge_id: str,
        *,
        close: bool,
        allow_loop: bool = False,
    ) -> SwitchingSimulationResult:
        edge = self.repository.require_edge(edge_id)
        if not edge.is_switchable:
            raise TopologyRepositoryError(f"Edge {edge_id} is not switchable")

        if close and not allow_loop and self.graph.creates_cycle_if_closed(edge_id):
            return SwitchingSimulationResult(
                edge_id=edge_id,
                requested_closed=close,
                accepted=False,
                reason="closing_switch_would_create_loop",
                original_closed=edge.is_closed,
                affected_nodes=(),
                repository=self.repository,
            )

        proposed = self.repository.with_edge_state(edge_id, is_closed=close)
        return SwitchingSimulationResult(
            edge_id=edge_id,
            requested_closed=close,
            accepted=True,
            reason=None,
            original_closed=edge.is_closed,
            affected_nodes=_energization_delta(self.repository, proposed),
            repository=proposed,
        )


def _energization_delta(
    original: InMemoryTopologyRepository,
    proposed: InMemoryTopologyRepository,
) -> tuple[str, ...]:
    before = _energized_nodes(original)
    after = _energized_nodes(proposed)
    return tuple(sorted(before.symmetric_difference(after)))


def _energized_nodes(repository: InMemoryTopologyRepository) -> set[str]:
    graph = ConnectivityGraph(repository)
    energized: set[str] = set()
    for node in repository.nodes:
        if node.node_type in SOURCE_NODE_TYPES:
            energized.update(graph.reachable_from(node.node_id))
    return energized
