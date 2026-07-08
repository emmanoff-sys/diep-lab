"""Feeder tracing services for ADMS topology graphs."""

from __future__ import annotations

from dataclasses import dataclass

from .graph import ConnectivityGraph, PathResult
from .repository import InMemoryTopologyRepository

SOURCE_NODE_TYPES = frozenset({"feeder", "substation"})


@dataclass(frozen=True)
class FeederTrace:
    feeder_id: str
    nodes: tuple[str, ...]
    edges: tuple[str, ...]


class FeederTracingService:
    def __init__(self, repository: InMemoryTopologyRepository) -> None:
        self.repository = repository
        self.graph = ConnectivityGraph(repository)

    def feeder_roots(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                node.node_id
                for node in self.repository.nodes
                if node.node_type in SOURCE_NODE_TYPES
            )
        )

    def trace_downstream(self, feeder_id: str) -> FeederTrace:
        self.repository.require_node(feeder_id)
        nodes = self.graph.reachable_from(feeder_id)
        edges = tuple(
            edge.edge_id
            for edge in self.repository.edges
            if edge.is_closed and edge.from_node in nodes and edge.to_node in nodes
        )
        return FeederTrace(feeder_id=feeder_id, nodes=nodes, edges=edges)

    def upstream_path(self, node_id: str) -> PathResult:
        self.repository.require_node(node_id)
        candidates = [
            self.graph.shortest_path(root, node_id)
            for root in self.feeder_roots()
            if self.graph.shortest_path(root, node_id).exists
        ]
        if not candidates:
            return PathResult(nodes=(), edges=())
        return sorted(candidates, key=lambda path: (len(path.edges), path.nodes))[0]

    def feeder_for_node(self, node_id: str) -> str | None:
        path = self.upstream_path(node_id)
        return path.nodes[0] if path.exists else None
