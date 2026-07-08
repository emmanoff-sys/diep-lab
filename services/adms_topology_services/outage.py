"""Outage impact analysis over ADMS topology graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .graph import ConnectivityGraph
from .repository import InMemoryTopologyRepository
from .tracing import SOURCE_NODE_TYPES


@dataclass(frozen=True)
class OutageImpact:
    outage_edge_id: str
    affected_nodes: tuple[str, ...]
    affected_edges: tuple[str, ...]
    isolation_boundaries: tuple[str, ...]
    customer_count: int


class OutageImpactService:
    def __init__(self, repository: InMemoryTopologyRepository) -> None:
        self.repository = repository
        self.graph = ConnectivityGraph(repository)

    def analyze_edge_outage(self, edge_id: str) -> OutageImpact:
        edge = self.repository.require_edge(edge_id)
        sources = tuple(
            node.node_id for node in self.repository.nodes if node.node_type in SOURCE_NODE_TYPES
        )
        energized_before = _energized_nodes(self.graph, sources)
        energized_after = _energized_nodes(
            self.graph,
            sources,
            blocked_edges=frozenset({edge.edge_id}),
        )
        affected_nodes = tuple(sorted(set(energized_before) - set(energized_after)))

        if not affected_nodes:
            candidate = edge.to_node if edge.from_node in energized_after else edge.from_node
            affected_nodes = self.graph.reachable_from(
                candidate,
                blocked_edges=frozenset({edge.edge_id}),
            )

        affected = set(affected_nodes)
        affected_edges = tuple(
            edge.edge_id
            for edge in self.repository.edges
            if edge.edge_id != edge_id and edge.from_node in affected and edge.to_node in affected
        )
        boundaries = tuple(
            edge.edge_id
            for edge in self.repository.edges
            if edge.is_switchable and ((edge.from_node in affected) ^ (edge.to_node in affected))
        )
        return OutageImpact(
            outage_edge_id=edge_id,
            affected_nodes=affected_nodes,
            affected_edges=affected_edges,
            isolation_boundaries=tuple(sorted(boundaries)),
            customer_count=sum(
                _customer_count(self.repository.require_node(node_id)) for node_id in affected
            ),
        )


def _energized_nodes(
    graph: ConnectivityGraph,
    sources: tuple[str, ...],
    *,
    blocked_edges: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    energized: set[str] = set()
    for source in sources:
        energized.update(graph.reachable_from(source, blocked_edges=blocked_edges))
    return tuple(sorted(energized))


def _customer_count(node: Any) -> int:
    metadata = node.metadata
    for value in (
        node.attrs.get("customer_count"),
        metadata.get("customer_count"),
        metadata.get("customers"),
    ):
        if isinstance(value, int) and value >= 0:
            return value
    return 1 if node.node_type in {"load", "meter"} else 0
