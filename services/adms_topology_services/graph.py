"""Connectivity graph services for ADMS topology snapshots."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .repository import InMemoryTopologyRepository, NetworkEdge, TopologyRepositoryError


@dataclass(frozen=True)
class PathResult:
    nodes: tuple[str, ...]
    edges: tuple[str, ...]

    @property
    def exists(self) -> bool:
        return bool(self.nodes)


class ConnectivityGraph:
    """Undirected electrical connectivity graph over repository edges."""

    def __init__(self, repository: InMemoryTopologyRepository) -> None:
        self.repository = repository

    def neighbors(self, node_id: str, *, include_open: bool = False) -> tuple[str, ...]:
        self.repository.require_node(node_id)
        return tuple(
            sorted(
                {
                    edge.other_node(node_id)
                    for edge in self.repository.edges_for_node(node_id, include_open=include_open)
                    if include_open or edge.is_closed
                }
            )
        )

    def incident_edges(
        self, node_id: str, *, include_open: bool = False
    ) -> tuple[NetworkEdge, ...]:
        self.repository.require_node(node_id)
        return self.repository.edges_for_node(node_id, include_open=include_open)

    def reachable_from(
        self,
        start_node: str,
        *,
        include_open: bool = False,
        blocked_edges: frozenset[str] = frozenset(),
    ) -> tuple[str, ...]:
        self.repository.require_node(start_node)
        visited = {start_node}
        queue: deque[str] = deque([start_node])
        while queue:
            node_id = queue.popleft()
            for edge in self.repository.edges_for_node(node_id, include_open=include_open):
                if edge.edge_id in blocked_edges or (not include_open and not edge.is_closed):
                    continue
                next_node = edge.other_node(node_id)
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(next_node)
        return tuple(sorted(visited))

    def connected_components(self, *, include_open: bool = False) -> tuple[tuple[str, ...], ...]:
        remaining = {node.node_id for node in self.repository.nodes}
        components: list[tuple[str, ...]] = []
        while remaining:
            start_node = sorted(remaining)[0]
            component = self.reachable_from(start_node, include_open=include_open)
            components.append(component)
            remaining.difference_update(component)
        return tuple(sorted(components, key=lambda component: component[0]))

    def shortest_path(
        self,
        start_node: str,
        end_node: str,
        *,
        include_open: bool = False,
        blocked_edges: frozenset[str] = frozenset(),
    ) -> PathResult:
        self.repository.require_node(start_node)
        self.repository.require_node(end_node)
        if start_node == end_node:
            return PathResult(nodes=(start_node,), edges=())

        queue: deque[str] = deque([start_node])
        visited = {start_node}
        parent: dict[str, tuple[str, str]] = {}

        while queue:
            node_id = queue.popleft()
            for edge in self.repository.edges_for_node(node_id, include_open=include_open):
                if edge.edge_id in blocked_edges or (not include_open and not edge.is_closed):
                    continue
                next_node = edge.other_node(node_id)
                if next_node in visited:
                    continue
                visited.add(next_node)
                parent[next_node] = (node_id, edge.edge_id)
                if next_node == end_node:
                    return _build_path(start_node, end_node, parent)
                queue.append(next_node)

        return PathResult(nodes=(), edges=())

    def edge_between(
        self, first_node: str, second_node: str, *, include_open: bool = True
    ) -> NetworkEdge | None:
        self.repository.require_node(first_node)
        self.repository.require_node(second_node)
        candidates = [
            edge
            for edge in self.repository.edges_for_node(first_node, include_open=include_open)
            if edge.other_node(first_node) == second_node and (include_open or edge.is_closed)
        ]
        return sorted(candidates, key=lambda edge: edge.edge_id)[0] if candidates else None

    def path_edges(self, path: PathResult) -> tuple[NetworkEdge, ...]:
        return tuple(self.repository.require_edge(edge_id) for edge_id in path.edges)

    def creates_cycle_if_closed(self, edge_id: str) -> bool:
        edge = self.repository.require_edge(edge_id)
        return self.shortest_path(
            edge.from_node,
            edge.to_node,
            blocked_edges=frozenset({edge.edge_id}),
        ).exists

    def has_cycles(self) -> bool:
        seen_edges: set[str] = set()
        for edge in self.repository.edges:
            if not edge.is_closed or edge.edge_id in seen_edges:
                continue
            if self.creates_cycle_if_closed(edge.edge_id):
                return True
            seen_edges.add(edge.edge_id)
        return False


def _build_path(
    start_node: str,
    end_node: str,
    parent: dict[str, tuple[str, str]],
) -> PathResult:
    nodes = [end_node]
    edges: list[str] = []
    current = end_node
    while current != start_node:
        if current not in parent:
            raise TopologyRepositoryError(f"Cannot reconstruct graph path to {end_node}")
        previous, edge_id = parent[current]
        nodes.append(previous)
        edges.append(edge_id)
        current = previous
    return PathResult(nodes=tuple(reversed(nodes)), edges=tuple(reversed(edges)))
