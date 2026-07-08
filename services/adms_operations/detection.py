"""OA-037 — deterministic outage detection over operational state."""

from __future__ import annotations

from .models import DetectedOutage, OutageGroup, OutageKind
from .state_view import OperationalNetworkView


class OutageDetectionService:
    """Identifies outages from the live operational network view.

    Candidate outages are CONNECTED dark components, attributed to the
    feeder that normally supplies them (reachability over normally-closed
    edges) — an open tie never merges two feeders' outages. All results are
    pure functions of topology + operational state: sorted tuples,
    content-derived identifiers, no clocks and no randomness.
    """

    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view

    def detect_loss_of_supply(self) -> tuple[DetectedOutage, ...]:
        """One candidate outage per connected de-energised region."""
        outages: list[DetectedOutage] = []
        for component in self.view.dark_components():
            feeder_id = self._home_feeder(component)
            outages.append(
                self._outage(
                    "loss_of_supply",
                    feeder_id,
                    component,
                    outage_id=f"outage:loss_of_supply:{feeder_id}:{component[0]}",
                )
            )
        return tuple(outages)

    def detect_source_loss(self) -> tuple[DetectedOutage, ...]:
        """Feeders whose source itself is unavailable or de-energised."""
        outages: list[DetectedOutage] = []
        for feeder_id in self.view.source_nodes():
            if self.view.source_healthy(feeder_id):
                continue
            extent = self.view.normal_supply_extent(feeder_id)
            outages.append(
                self._outage(
                    "source_loss",
                    feeder_id,
                    extent,
                    outage_id=f"outage:source_loss:{feeder_id}",
                )
            )
        return tuple(outages)

    def identify_feeder_outages(self) -> tuple[DetectedOutage, ...]:
        """Feeders whose entire normal-supply extent is dark."""
        outages: list[DetectedOutage] = []
        energized = set(self.view.energized_nodes())
        sources = set(self.view.source_nodes())
        for feeder_id in self.view.source_nodes():
            extent = tuple(sorted(set(self.view.normal_supply_extent(feeder_id)) - sources))
            if extent and not (set(extent) & energized):
                outages.append(
                    self._outage(
                        "feeder_outage",
                        feeder_id,
                        extent,
                        outage_id=f"outage:feeder_outage:{feeder_id}",
                    )
                )
        return tuple(outages)

    def group_candidates(self, outages: tuple[DetectedOutage, ...]) -> tuple[OutageGroup, ...]:
        """Group outages whose affected-node sets overlap (union-find)."""
        parents = list(range(len(outages)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        node_sets = [set(outage.affected_nodes) for outage in outages]
        for i in range(len(outages)):
            for j in range(i + 1, len(outages)):
                if node_sets[i] & node_sets[j]:
                    parents[find(j)] = find(i)

        buckets: dict[int, list[DetectedOutage]] = {}
        for index, outage in enumerate(outages):
            buckets.setdefault(find(index), []).append(outage)

        groups: list[OutageGroup] = []
        ordered = sorted(buckets.values(), key=lambda member: member[0].outage_id)
        for position, members in enumerate(ordered, start=1):
            members_sorted = tuple(sorted(members, key=lambda o: o.outage_id))
            affected = tuple(sorted(set().union(*(set(o.affected_nodes) for o in members_sorted))))
            feeders = tuple(sorted({o.feeder_id for o in members_sorted}))
            groups.append(
                OutageGroup(
                    group_id=f"outage-group:{position:03d}",
                    outages=members_sorted,
                    affected_nodes=affected,
                    feeder_ids=feeders,
                    customer_count=sum(self.view.node_customer_count(node) for node in affected),
                )
            )
        return tuple(groups)

    def detect_all(self) -> tuple[OutageGroup, ...]:
        """Full detection pass: dark components + source loss, grouped."""
        outages = self.detect_loss_of_supply() + self.detect_source_loss()
        return self.group_candidates(outages)

    def _home_feeder(self, component: tuple[str, ...]) -> str:
        """First feeder whose normal supply extent covers the component."""
        component_set = set(component)
        for feeder_id in self.view.source_nodes():
            if component_set & set(self.view.normal_supply_extent(feeder_id)):
                return feeder_id
        return "unassigned"

    def _outage(
        self,
        kind: OutageKind,
        feeder_id: str,
        affected: tuple[str, ...],
        *,
        outage_id: str,
    ) -> DetectedOutage:
        return DetectedOutage(
            outage_id=outage_id,
            kind=kind,
            feeder_id=feeder_id,
            affected_nodes=affected,
            candidate_cause_edges=self._candidate_causes(affected),
            customer_count=sum(self.view.node_customer_count(node) for node in affected),
        )

    def _candidate_causes(self, affected: tuple[str, ...]) -> tuple[str, ...]:
        """Non-conducting edges on or inside the dark region boundary."""
        affected_set = set(affected)
        causes = {
            edge.edge_id
            for edge in self.view.topology.edges
            if (edge.from_node in affected_set or edge.to_node in affected_set)
            and not self.view.edge_conducting(edge.edge_id)
        }
        return tuple(sorted(causes))
