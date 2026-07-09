"""OA-040 — restoration candidate analysis after isolation."""

from __future__ import annotations

from collections import deque

from .models import IsolationBoundary, RestorationCandidate
from .state_view import OperationalNetworkView


class RestorationCandidateService:
    """Rule-based restoration analysis: alternative supply paths through
    open, operable tie switches from healthy energised feeders, with
    capacity awareness from static edge ratings. No optimisation, no power
    flow — those are explicitly out of WP-009 scope."""

    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view

    def available_feeders(self) -> tuple[str, ...]:
        return tuple(
            feeder for feeder in self.view.source_nodes() if self.view.source_healthy(feeder)
        )

    def candidates(
        self,
        affected_nodes: tuple[str, ...],
        boundary: IsolationBoundary,
    ) -> tuple[RestorationCandidate, ...]:
        """Restoration options for the isolated region, best-ranked first.

        Ranking is deterministic: capacity-satisfying candidates first, then
        most customers restored, then most nodes, then candidate id.
        """
        region = set(affected_nodes)
        blocked = frozenset(boundary.safe_isolation_edges)
        energized = set(self.view.energized_nodes(blocked_edges=blocked))

        found: list[RestorationCandidate] = []
        for edge in self.view.topology.edges:
            if not edge.is_switchable:
                continue
            connectivity = self.view.operational_state.connectivity_state(edge.edge_id)
            if connectivity.closed or not connectivity.available:
                continue
            # NOTE: edges in the isolation set are NOT skipped — an open tie
            # switch is typically both an isolation boundary point and the
            # restoration path; SR-003/SR-004 guard the close operation.
            sides = {edge.from_node, edge.to_node}
            dark_side = sides & region - energized
            live_side = sides & energized - region
            if not dark_side or not live_side:
                continue
            live_node = sorted(live_side)[0]
            dark_node = sorted(dark_side)[0]
            supply = self._supply_path(live_node, blocked)
            if supply is None:
                continue
            feeder_id, path_nodes, path_edges = supply
            restored = self._restorable_region(dark_node, region, blocked)
            load_kw = sum(self.view.node_load_kw(node) for node in restored)
            capacity = self._path_capacity(path_edges + (edge.edge_id,))
            found.append(
                RestorationCandidate(
                    candidate_id=f"restore:{edge.edge_id}:{feeder_id}",
                    tie_edge_id=edge.edge_id,
                    supply_feeder_id=feeder_id,
                    supply_path_nodes=path_nodes,
                    restored_nodes=restored,
                    restored_load_kw=load_kw,
                    restored_customer_count=sum(
                        self.view.node_customer_count(node) for node in restored
                    ),
                    path_capacity_kw=capacity,
                    capacity_ok=capacity is None or load_kw <= capacity,
                )
            )

        return tuple(
            sorted(
                found,
                key=lambda candidate: (
                    not candidate.capacity_ok,
                    -candidate.restored_customer_count,
                    -len(candidate.restored_nodes),
                    candidate.candidate_id,
                ),
            )
        )

    def _supply_path(
        self, start_node: str, blocked: frozenset[str]
    ) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
        """Shortest conducting path from `start_node` back to a healthy source."""
        sources = {
            feeder for feeder in self.view.source_nodes() if self.view.source_healthy(feeder)
        }
        parents: dict[str, tuple[str, str] | None] = {start_node: None}
        queue: deque[str] = deque([start_node])
        while queue:
            node_id = queue.popleft()
            if node_id in sources:
                path_nodes: list[str] = [node_id]
                path_edges: list[str] = []
                cursor = node_id
                hop = parents[cursor]
                while hop is not None:
                    parent_node, via_edge = hop
                    path_nodes.append(parent_node)
                    path_edges.append(via_edge)
                    cursor = parent_node
                    hop = parents[cursor]
                # path_nodes is built source-first back toward the tie side,
                # which is exactly the operator-facing supply direction.
                return node_id, tuple(path_nodes), tuple(path_edges)
            for edge in self.view.topology.edges_for_node(node_id, include_open=True):
                if edge.edge_id in blocked or not self.view.edge_conducting(edge.edge_id):
                    continue
                next_node = edge.other_node(node_id)
                if next_node in parents or not self.view.node_traversable(next_node):
                    continue
                parents[next_node] = (node_id, edge.edge_id)
                queue.append(next_node)
        return None

    def _restorable_region(
        self, entry_node: str, region: set[str], blocked: frozenset[str]
    ) -> tuple[str, ...]:
        """Region nodes reachable from the tie entry point after isolation."""
        reachable = self.view.reachable_operationally(entry_node, blocked_edges=blocked)
        return tuple(sorted(set(reachable) & region))

    def _path_capacity(self, edge_ids: tuple[str, ...]) -> float | None:
        ratings = [
            edge.rating_kw
            for edge in (self.view.topology.require_edge(edge_id) for edge_id in edge_ids)
            if edge.rating_kw is not None
        ]
        return min(ratings) if ratings else None
