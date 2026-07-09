"""Hypothetical network state overlay shared by WP-010 services.

Every analytical question in WP-010 is a variant of "what would be
energised IF ...". This module answers it purely: a real
`OperationalNetworkView` (WP-009) plus override sets, evaluated without
mutating WP-008 state. Two bases are supported:

- ``live``: current operational state (WP-008) with overrides applied;
- ``normal``: the as-designed network (normally-closed switch positions,
  every device available) with overrides applied — used to test whether a
  single hypothetical failure explains an observation.
"""

from __future__ import annotations

from collections import deque
from typing import Literal

from services.adms_operations import OperationalNetworkView

from .models import FeederLoading, OperationalIntelligenceError

OverlayBase = Literal["live", "normal"]


class HypotheticalNetworkState:
    def __init__(
        self,
        view: OperationalNetworkView,
        *,
        base: OverlayBase = "live",
        failed_edges: frozenset[str] = frozenset(),
        opened_edges: frozenset[str] = frozenset(),
        closed_edges: frozenset[str] = frozenset(),
        failed_sources: frozenset[str] = frozenset(),
    ) -> None:
        self.view = view
        self.base = base
        self.failed_edges = failed_edges
        self.opened_edges = opened_edges
        self.closed_edges = closed_edges
        self.failed_sources = failed_sources
        self._known_edges = {edge.edge_id for edge in view.topology.edges}
        self._validate_targets()

    def _validate_targets(self) -> None:
        for edge_id in sorted(self.failed_edges | self.opened_edges | self.closed_edges):
            if edge_id not in self._known_edges:
                raise OperationalIntelligenceError(f"unknown edge in overlay: {edge_id}")
        sources = set(self.view.source_nodes())
        for source_id in sorted(self.failed_sources):
            if source_id not in sources:
                raise OperationalIntelligenceError(f"unknown source in overlay: {source_id}")

    def edge_conducting(self, edge_id: str) -> bool:
        if edge_id in self.failed_edges or edge_id in self.opened_edges:
            return False
        if edge_id in self.closed_edges:
            return True
        if self.base == "normal":
            return bool(self.view.topology.require_edge(edge_id).normally_closed)
        return self.view.edge_conducting(edge_id)

    def source_healthy(self, source_id: str) -> bool:
        if source_id in self.failed_sources:
            return False
        if self.base == "normal":
            return True
        return self.view.source_healthy(source_id)

    def node_traversable(self, node_id: str) -> bool:
        if self.base == "normal":
            return True
        return self.view.node_traversable(node_id)

    def energized_nodes(self) -> tuple[str, ...]:
        energized: set[str] = set()
        for source in self.view.source_nodes():
            if self.source_healthy(source):
                energized.update(self._reach(source))
        return tuple(sorted(energized))

    def feeder_loading(self) -> tuple[FeederLoading, ...]:
        """Per-source served load with exclusive attribution.

        Each node is attributed to the first healthy source (sorted order)
        that reaches it — deterministic, and exact for the radial post-
        switching states WP-010 evaluates.
        """
        claimed: set[str] = set()
        loading: list[FeederLoading] = []
        for source in self.view.source_nodes():
            if not self.source_healthy(source):
                loading.append(FeederLoading(source, 0.0, 0))
                continue
            served = self._reach(source) - claimed
            claimed.update(served)
            loading.append(
                FeederLoading(
                    feeder_id=source,
                    served_load_kw=sum(self.view.node_load_kw(node) for node in served),
                    served_customer_count=sum(
                        self.view.node_customer_count(node) for node in served
                    ),
                )
            )
        return tuple(loading)

    def _reach(self, start_node: str) -> set[str]:
        visited = {start_node}
        queue: deque[str] = deque([start_node])
        while queue:
            node_id = queue.popleft()
            for edge in self.view.topology.edges_for_node(node_id, include_open=True):
                if not self.edge_conducting(edge.edge_id):
                    continue
                next_node = edge.other_node(node_id)
                if next_node in visited or not self.node_traversable(next_node):
                    continue
                visited.add(next_node)
                queue.append(next_node)
        return visited
