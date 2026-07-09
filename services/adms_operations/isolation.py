"""OA-038 — isolation boundary analysis for detected outage regions."""

from __future__ import annotations

from .models import IsolationBoundary, IsolationPoint
from .state_view import OperationalNetworkView


class IsolationBoundaryService:
    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view

    def discover_isolation_points(
        self, affected_nodes: tuple[str, ...]
    ) -> tuple[IsolationPoint, ...]:
        """Every edge crossing the region boundary, with live device state."""
        region = set(affected_nodes)
        points: list[IsolationPoint] = []
        for edge in self.view.topology.edges:
            if (edge.from_node in region) == (edge.to_node in region):
                continue
            connectivity = self.view.operational_state.connectivity_state(edge.edge_id)
            points.append(
                IsolationPoint(
                    edge_id=edge.edge_id,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    switchable=edge.is_switchable,
                    closed=connectivity.closed,
                    available=connectivity.available,
                )
            )
        return tuple(sorted(points, key=lambda point: point.edge_id))

    def safe_isolation_candidates(
        self, points: tuple[IsolationPoint, ...]
    ) -> tuple[IsolationPoint, ...]:
        """Boundary points that can actually be operated to isolate."""
        return tuple(point for point in points if point.operable)

    def verify_boundary(
        self,
        affected_nodes: tuple[str, ...],
        isolation_edges: tuple[str, ...],
    ) -> tuple[bool, tuple[str, ...]]:
        """Would opening `isolation_edges` electrically isolate the region?

        Simulates the isolation set as blocked and recomputes energisation
        from healthy sources over live operational state. Returns
        (verified, still-energised region nodes as evidence).
        """
        region = set(affected_nodes)
        energized_after = set(self.view.energized_nodes(blocked_edges=frozenset(isolation_edges)))
        leaks = tuple(sorted(region & energized_after))
        return (not leaks, leaks)

    def analyze(self, subject_id: str, affected_nodes: tuple[str, ...]) -> IsolationBoundary:
        """Full boundary analysis with dependency validation diagnostics."""
        points = self.discover_isolation_points(affected_nodes)
        safe = self.safe_isolation_candidates(points)
        diagnostics: list[str] = []

        for point in points:
            if not point.switchable:
                diagnostics.append(
                    f"boundary edge {point.edge_id} is not switchable; "
                    "isolation must rely on the remaining boundary points"
                )
            elif not point.available:
                diagnostics.append(
                    f"isolation point {point.edge_id} is reported unavailable "
                    "by operational state and cannot be operated"
                )

        # Dependency validation: the safe set must cover every conducting
        # boundary crossing, otherwise the region cannot be de-energised by
        # switching alone.
        safe_ids = tuple(point.edge_id for point in safe)
        uncovered = tuple(
            point.edge_id
            for point in points
            if point.closed and point.available and not point.operable
        )
        if uncovered:
            diagnostics.append(
                "conducting boundary edges without operable isolation: " + ", ".join(uncovered)
            )

        verified, leaks = self.verify_boundary(affected_nodes, safe_ids)
        if not verified:
            diagnostics.append(
                "boundary not verified: region nodes still energised after "
                "simulated isolation: " + ", ".join(leaks)
            )

        return IsolationBoundary(
            subject_id=subject_id,
            isolation_points=points,
            safe_isolation_edges=safe_ids,
            verified=verified,
            unisolated_nodes=leaks,
            diagnostics=tuple(diagnostics),
        )
