"""Shared operational-network view helpers for WP-009 services.

Every WP-009 service needs the same question answered: which nodes are
energised RIGHT NOW, honouring both static topology and live operational
state (WP-008)? This module centralises that traversal so detection,
isolation, switching, and restoration cannot drift apart. It consumes the
WP-007/WP-008 layers as-is — no redesign.
"""

from __future__ import annotations

from collections import deque

from services.adms_operational_state import OperationalStateService
from services.adms_topology_services import InMemoryTopologyRepository
from services.adms_topology_services.tracing import SOURCE_NODE_TYPES


class OperationalNetworkView:
    def __init__(
        self,
        topology: InMemoryTopologyRepository,
        operational_state: OperationalStateService,
    ) -> None:
        self.topology = topology
        self.operational_state = operational_state

    def source_nodes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                node.node_id for node in self.topology.nodes if node.node_type in SOURCE_NODE_TYPES
            )
        )

    def source_healthy(self, source_id: str) -> bool:
        state = self.operational_state.asset_state(source_id, asset_kind="node")
        if state is None:
            return True
        if not state.available:
            return False
        return state.energized is not False

    def edge_conducting(self, edge_id: str) -> bool:
        connectivity = self.operational_state.connectivity_state(edge_id)
        return connectivity.closed and connectivity.available

    def node_traversable(self, node_id: str) -> bool:
        return self.operational_state.device_available(node_id, asset_kind="node")

    def energized_nodes(
        self,
        *,
        blocked_edges: frozenset[str] = frozenset(),
        sources: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        """Nodes reachable from healthy sources over conducting edges."""
        roots = sources if sources is not None else self.source_nodes()
        energized: set[str] = set()
        for source in roots:
            if not self.source_healthy(source):
                continue
            energized.update(self._reach(source, blocked_edges=blocked_edges))
        return tuple(sorted(energized))

    def reachable_over_topology(self, start_node: str) -> tuple[str, ...]:
        """Static reachability including open switches (network extent)."""
        self.topology.require_node(start_node)
        visited = {start_node}
        queue: deque[str] = deque([start_node])
        while queue:
            node_id = queue.popleft()
            for edge in self.topology.edges_for_node(node_id, include_open=True):
                next_node = edge.other_node(node_id)
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(next_node)
        return tuple(sorted(visited))

    def reachable_operationally(
        self,
        start_node: str,
        *,
        blocked_edges: frozenset[str] = frozenset(),
    ) -> tuple[str, ...]:
        return tuple(sorted(self._reach(start_node, blocked_edges=blocked_edges)))

    def normal_supply_extent(self, source_id: str) -> tuple[str, ...]:
        """Nodes normally supplied by `source_id`: reachability over
        normally-closed edges only. Open ties do not extend a feeder's
        normal extent — this is the attribution basis for outage regions."""
        self.topology.require_node(source_id)
        visited = {source_id}
        queue: deque[str] = deque([source_id])
        while queue:
            node_id = queue.popleft()
            for edge in self.topology.edges_for_node(node_id, include_open=True):
                if not edge.normally_closed:
                    continue
                next_node = edge.other_node(node_id)
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append(next_node)
        return tuple(sorted(visited))

    def dark_components(self) -> tuple[tuple[str, ...], ...]:
        """Connected components of de-energised nodes over the static
        network (any edge whose endpoints are both dark keeps them in the
        same candidate region, switch position notwithstanding)."""
        dark = set(node.node_id for node in self.topology.nodes) - set(self.energized_nodes())
        components: list[tuple[str, ...]] = []
        remaining = set(dark)
        while remaining:
            start = sorted(remaining)[0]
            component = {start}
            queue: deque[str] = deque([start])
            while queue:
                node_id = queue.popleft()
                for edge in self.topology.edges_for_node(node_id, include_open=True):
                    next_node = edge.other_node(node_id)
                    if next_node in dark and next_node not in component:
                        component.add(next_node)
                        queue.append(next_node)
            components.append(tuple(sorted(component)))
            remaining -= component
        return tuple(sorted(components))

    def _reach(self, start_node: str, *, blocked_edges: frozenset[str]) -> set[str]:
        self.topology.require_node(start_node)
        visited = {start_node}
        queue: deque[str] = deque([start_node])
        while queue:
            node_id = queue.popleft()
            for edge in self.topology.edges_for_node(node_id, include_open=True):
                if edge.edge_id in blocked_edges or not self.edge_conducting(edge.edge_id):
                    continue
                next_node = edge.other_node(node_id)
                if next_node in visited or not self.node_traversable(next_node):
                    continue
                visited.add(next_node)
                queue.append(next_node)
        return visited

    def node_load_kw(self, node_id: str) -> float:
        node = self.topology.require_node(node_id)
        for value in (
            node.attrs.get("base_load_kw"),
            node.metadata.get("base_load_kw"),
            node.metadata.get("load_kw"),
        ):
            if isinstance(value, (int, float)) and value >= 0:
                return float(value)
        return 0.0

    def node_customer_count(self, node_id: str) -> int:
        node = self.topology.require_node(node_id)
        for value in (
            node.attrs.get("customer_count"),
            node.metadata.get("customer_count"),
            node.metadata.get("customers"),
        ):
            if isinstance(value, int) and value >= 0:
                return value
        return 1 if node.node_type in {"load", "meter"} else 0
