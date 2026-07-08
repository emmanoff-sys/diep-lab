"""Network model repository for mapped ADMS topology snapshots."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from services.adms_topology_import.mapping import MappedTopology


class TopologyRepositoryError(ValueError):
    """Raised when a mapped topology cannot be indexed as a network model."""


@dataclass(frozen=True)
class NetworkNode:
    node_id: str
    node_type: str
    name: str | None
    latitude: float | None
    longitude: float | None
    nominal_kv: float | None
    phases: str | None
    attrs: dict[str, Any]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NetworkNode:
        return cls(
            node_id=_required_text(row, "node_id"),
            node_type=_required_text(row, "node_type"),
            name=_optional_text(row.get("name")),
            latitude=_optional_float(row.get("latitude")),
            longitude=_optional_float(row.get("longitude")),
            nominal_kv=_optional_float(row.get("nominal_kv")),
            phases=_optional_text(row.get("phases")),
            attrs=dict(row.get("attrs") or {}),
        )

    @property
    def external_id(self) -> str | None:
        value = self.attrs.get("external_id")
        return value if isinstance(value, str) else None

    @property
    def metadata(self) -> dict[str, Any]:
        value = self.attrs.get("metadata")
        return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class NetworkEdge:
    edge_id: str
    from_node: str
    to_node: str
    edge_type: str
    is_switchable: bool
    normally_closed: bool
    is_closed: bool
    rating_kw: float | None
    phases: str | None
    attrs: dict[str, Any]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> NetworkEdge:
        return cls(
            edge_id=_required_text(row, "edge_id"),
            from_node=_required_text(row, "from_node"),
            to_node=_required_text(row, "to_node"),
            edge_type=_required_text(row, "edge_type"),
            is_switchable=_required_bool(row, "is_switchable"),
            normally_closed=_required_bool(row, "normally_closed"),
            is_closed=_required_bool(row, "is_closed"),
            rating_kw=_optional_float(row.get("rating_kw")),
            phases=_optional_text(row.get("phases")),
            attrs=dict(row.get("attrs") or {}),
        )

    @property
    def external_id(self) -> str | None:
        value = self.attrs.get("external_id")
        return value if isinstance(value, str) else None

    def other_node(self, node_id: str) -> str:
        if node_id == self.from_node:
            return self.to_node
        if node_id == self.to_node:
            return self.from_node
        raise TopologyRepositoryError(f"Edge {self.edge_id} is not connected to node {node_id}")

    def with_state(self, *, is_closed: bool) -> NetworkEdge:
        return replace(self, is_closed=is_closed)


@dataclass(frozen=True)
class TopologySnapshot:
    source_system: str
    external_model_id: str
    external_model_version: str
    nodes: tuple[NetworkNode, ...]
    edges: tuple[NetworkEdge, ...]


class InMemoryTopologyRepository:
    """Immutable in-memory index over the WP-006-08 mapped topology contract."""

    def __init__(self, snapshot: TopologySnapshot) -> None:
        self.snapshot = snapshot
        self._nodes = _index_by_node_id(snapshot.nodes)
        self._edges = _index_by_edge_id(snapshot.edges)
        self._external_nodes = _index_external_nodes(snapshot.nodes)
        self._external_edges = _index_external_edges(snapshot.edges)
        self._node_types = _index_node_types(snapshot.nodes)
        self._edge_types = _index_edge_types(snapshot.edges)
        self._node_edges = _index_node_edges(snapshot.nodes, snapshot.edges)

    @classmethod
    def from_mapped_topology(cls, mapped: MappedTopology) -> InMemoryTopologyRepository:
        return cls(
            TopologySnapshot(
                source_system=mapped.source_system,
                external_model_id=mapped.external_model_id,
                external_model_version=mapped.external_model_version,
                nodes=tuple(NetworkNode.from_row(row) for row in mapped.nodes),
                edges=tuple(NetworkEdge.from_row(row) for row in mapped.edges),
            )
        )

    @property
    def nodes(self) -> tuple[NetworkNode, ...]:
        return tuple(sorted(self.snapshot.nodes, key=lambda node: node.node_id))

    @property
    def edges(self) -> tuple[NetworkEdge, ...]:
        return tuple(sorted(self.snapshot.edges, key=lambda edge: edge.edge_id))

    def get_node(self, node_id: str) -> NetworkNode | None:
        return self._nodes.get(node_id)

    def require_node(self, node_id: str) -> NetworkNode:
        node = self.get_node(node_id)
        if node is None:
            raise TopologyRepositoryError(f"Unknown network node: {node_id}")
        return node

    def get_edge(self, edge_id: str) -> NetworkEdge | None:
        return self._edges.get(edge_id)

    def require_edge(self, edge_id: str) -> NetworkEdge:
        edge = self.get_edge(edge_id)
        if edge is None:
            raise TopologyRepositoryError(f"Unknown network edge: {edge_id}")
        return edge

    def find_node_by_external_id(self, external_id: str) -> NetworkNode | None:
        return self._external_nodes.get(external_id)

    def find_edge_by_external_id(self, external_id: str) -> NetworkEdge | None:
        return self._external_edges.get(external_id)

    def nodes_by_type(self, node_type: str) -> tuple[NetworkNode, ...]:
        return self._node_types.get(node_type, ())

    def edges_by_type(self, edge_type: str) -> tuple[NetworkEdge, ...]:
        return self._edge_types.get(edge_type, ())

    def edges_for_node(self, node_id: str, *, include_open: bool = True) -> tuple[NetworkEdge, ...]:
        edges = self._node_edges.get(node_id, ())
        if include_open:
            return edges
        return tuple(edge for edge in edges if edge.is_closed)

    def with_edge_state(self, edge_id: str, *, is_closed: bool) -> InMemoryTopologyRepository:
        self.require_edge(edge_id)
        return InMemoryTopologyRepository(
            replace(
                self.snapshot,
                edges=tuple(
                    edge.with_state(is_closed=is_closed) if edge.edge_id == edge_id else edge
                    for edge in self.snapshot.edges
                ),
            )
        )


def _index_by_node_id(nodes: tuple[NetworkNode, ...]) -> dict[str, NetworkNode]:
    index: dict[str, NetworkNode] = {}
    for node in nodes:
        if node.node_id in index:
            raise TopologyRepositoryError(f"Duplicate network node: {node.node_id}")
        index[node.node_id] = node
    return index


def _index_by_edge_id(edges: tuple[NetworkEdge, ...]) -> dict[str, NetworkEdge]:
    index: dict[str, NetworkEdge] = {}
    for edge in edges:
        if edge.edge_id in index:
            raise TopologyRepositoryError(f"Duplicate network edge: {edge.edge_id}")
        index[edge.edge_id] = edge
    return index


def _index_external_nodes(nodes: tuple[NetworkNode, ...]) -> dict[str, NetworkNode]:
    return {node.external_id: node for node in nodes if node.external_id is not None}


def _index_external_edges(edges: tuple[NetworkEdge, ...]) -> dict[str, NetworkEdge]:
    return {edge.external_id: edge for edge in edges if edge.external_id is not None}


def _index_node_types(nodes: tuple[NetworkNode, ...]) -> dict[str, tuple[NetworkNode, ...]]:
    grouped: dict[str, list[NetworkNode]] = {}
    for node in nodes:
        grouped.setdefault(node.node_type, []).append(node)
    return {
        node_type: tuple(sorted(items, key=lambda node: node.node_id))
        for node_type, items in grouped.items()
    }


def _index_edge_types(edges: tuple[NetworkEdge, ...]) -> dict[str, tuple[NetworkEdge, ...]]:
    grouped: dict[str, list[NetworkEdge]] = {}
    for edge in edges:
        grouped.setdefault(edge.edge_type, []).append(edge)
    return {
        edge_type: tuple(sorted(items, key=lambda edge: edge.edge_id))
        for edge_type, items in grouped.items()
    }


def _index_node_edges(
    nodes: tuple[NetworkNode, ...],
    edges: tuple[NetworkEdge, ...],
) -> dict[str, tuple[NetworkEdge, ...]]:
    node_ids = {node.node_id for node in nodes}
    grouped: dict[str, list[NetworkEdge]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if edge.from_node not in node_ids or edge.to_node not in node_ids:
            raise TopologyRepositoryError(f"Edge {edge.edge_id} references an unknown node")
        grouped[edge.from_node].append(edge)
        grouped[edge.to_node].append(edge)
    return {
        node_id: tuple(sorted(items, key=lambda edge: edge.edge_id))
        for node_id, items in grouped.items()
    }


def _required_text(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TopologyRepositoryError(f"Required text field is missing: {field}")
    return value


def _required_bool(row: dict[str, Any], field: str) -> bool:
    value = row.get(field)
    if not isinstance(value, bool):
        raise TopologyRepositoryError(f"Required boolean field is missing: {field}")
    return value


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TopologyRepositoryError("Boolean value cannot be converted to a network number")
    if isinstance(value, int | float):
        return float(value)
    raise TopologyRepositoryError(f"Invalid numeric network value: {value!r}")
