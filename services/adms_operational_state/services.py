"""Live operational network state services."""

from __future__ import annotations

from dataclasses import dataclass

from services.adms_topology_services import InMemoryTopologyRepository
from services.adms_topology_services.tracing import SOURCE_NODE_TYPES

from .models import OperationalAssetState
from .repository import InMemoryOperationalStateRepository


@dataclass(frozen=True)
class ConnectivityState:
    from_node: str
    to_node: str
    edge_id: str
    closed: bool
    available: bool
    energized: bool | None


@dataclass(frozen=True)
class FeederEnergisation:
    feeder_id: str
    energized_nodes: tuple[str, ...]
    deenergized_nodes: tuple[str, ...]


class OperationalStateService:
    def __init__(
        self,
        topology: InMemoryTopologyRepository,
        repository: InMemoryOperationalStateRepository,
    ) -> None:
        self.topology = topology
        self.repository = repository

    def asset_state(self, asset_id: str, *, asset_kind: str) -> OperationalAssetState | None:
        if asset_kind not in {"node", "edge"}:
            return None
        return self.repository.get_state(asset_id, asset_kind=asset_kind)

    def device_available(self, asset_id: str, *, asset_kind: str) -> bool:
        state = self.asset_state(asset_id, asset_kind=asset_kind)
        return True if state is None else state.available

    def connectivity_state(self, edge_id: str) -> ConnectivityState:
        edge = self.topology.require_edge(edge_id)
        state = self.repository.get_state(edge_id, asset_kind="edge")
        return ConnectivityState(
            from_node=edge.from_node,
            to_node=edge.to_node,
            edge_id=edge.edge_id,
            closed=_edge_closed(edge.is_closed, state),
            available=True if state is None else state.available,
            energized=None if state is None else state.energized,
        )

    def network_states(self) -> tuple[OperationalAssetState, ...]:
        return self.repository.current_states()

    def feeder_energisation(self, feeder_id: str) -> FeederEnergisation:
        self.topology.require_node(feeder_id)
        energized = self._reachable_energized(feeder_id)
        all_nodes = self._reachable_topology_nodes(feeder_id)
        return FeederEnergisation(
            feeder_id=feeder_id,
            energized_nodes=tuple(sorted(energized)),
            deenergized_nodes=tuple(sorted(all_nodes - energized)),
        )

    def feeders(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                node.node_id for node in self.topology.nodes if node.node_type in SOURCE_NODE_TYPES
            )
        )

    def _reachable_topology_nodes(self, feeder_id: str) -> set[str]:
        visited = {feeder_id}
        queue = [feeder_id]
        while queue:
            node_id = queue.pop(0)
            for edge in self.topology.edges_for_node(node_id, include_open=True):
                next_node = edge.other_node(node_id)
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(next_node)
        return visited

    def _reachable_energized(self, feeder_id: str) -> set[str]:
        visited = {feeder_id}
        queue = [feeder_id]
        while queue:
            node_id = queue.pop(0)
            for edge in self.topology.edges_for_node(node_id, include_open=True):
                connectivity = self.connectivity_state(edge.edge_id)
                if not connectivity.closed or not connectivity.available:
                    continue
                next_node = edge.other_node(node_id)
                if not self.device_available(next_node, asset_kind="node"):
                    continue
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(next_node)
        return visited


def _edge_closed(static_closed: bool, state: OperationalAssetState | None) -> bool:
    if state is None:
        return static_closed
    if state.switch_status == "open" or state.breaker_status == "open":
        return False
    if state.switch_status == "closed" or state.breaker_status == "closed":
        return True
    return static_closed
