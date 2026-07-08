"""Read-only network query services."""

from __future__ import annotations

from dataclasses import dataclass

from .graph import ConnectivityGraph
from .repository import InMemoryTopologyRepository, NetworkEdge, NetworkNode


@dataclass(frozen=True)
class ConnectedAsset:
    node: NetworkNode
    via_edges: tuple[NetworkEdge, ...]


class NetworkQueryService:
    """Lookup and relationship queries over a topology repository."""

    def __init__(self, repository: InMemoryTopologyRepository) -> None:
        self.repository = repository
        self.graph = ConnectivityGraph(repository)

    def get_node(self, node_id: str) -> NetworkNode | None:
        return self.repository.get_node(node_id)

    def get_edge(self, edge_id: str) -> NetworkEdge | None:
        return self.repository.get_edge(edge_id)

    def find_node_by_external_id(self, external_id: str) -> NetworkNode | None:
        return self.repository.find_node_by_external_id(external_id)

    def find_edge_by_external_id(self, external_id: str) -> NetworkEdge | None:
        return self.repository.find_edge_by_external_id(external_id)

    def nodes_by_type(self, node_type: str) -> tuple[NetworkNode, ...]:
        return self.repository.nodes_by_type(node_type)

    def edges_by_type(self, edge_type: str) -> tuple[NetworkEdge, ...]:
        return self.repository.edges_by_type(edge_type)

    def connected_assets(
        self, node_id: str, *, include_open: bool = False
    ) -> tuple[ConnectedAsset, ...]:
        assets = []
        for neighbor_id in self.graph.neighbors(node_id, include_open=include_open):
            edge = self.graph.edge_between(node_id, neighbor_id, include_open=include_open)
            assets.append(
                ConnectedAsset(
                    node=self.repository.require_node(neighbor_id),
                    via_edges=(edge,) if edge is not None else (),
                )
            )
        return tuple(sorted(assets, key=lambda asset: asset.node.node_id))
