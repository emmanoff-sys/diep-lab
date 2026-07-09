"""OA-050 — non-destructive scenario simulation.

Scenarios are data; simulating one never mutates WP-008 operational
state. Replaying the same scenario over the same state yields the same
outcome — asserted by the WP-010 test suite.
"""

from __future__ import annotations

from services.adms_operations import OperationalNetworkView

from .models import (
    OperationalIntelligenceError,
    Scenario,
    ScenarioComparison,
    ScenarioOutcome,
)
from .overlay import HypotheticalNetworkState


class ScenarioSimulationService:
    def __init__(self, view: OperationalNetworkView) -> None:
        self.view = view

    def simulate(self, scenario: Scenario) -> ScenarioOutcome:
        overlay = self._overlay(scenario)
        before = self.view.energized_nodes()
        after = overlay.energized_nodes()
        de_energized = tuple(sorted(set(before) - set(after)))
        re_energized = tuple(sorted(set(after) - set(before)))
        return ScenarioOutcome(
            scenario_id=scenario.scenario_id,
            description=scenario.description,
            energized_before=before,
            energized_after=after,
            de_energized_nodes=de_energized,
            re_energized_nodes=re_energized,
            lost_load_kw=sum(self.view.node_load_kw(node) for node in de_energized),
            lost_customer_count=sum(self.view.node_customer_count(node) for node in de_energized),
            restored_load_kw=sum(self.view.node_load_kw(node) for node in re_energized),
            restored_customer_count=sum(
                self.view.node_customer_count(node) for node in re_energized
            ),
            feeder_loading=overlay.feeder_loading(),
        )

    def compare(self, scenarios: tuple[Scenario, ...]) -> ScenarioComparison:
        """Simulate every scenario and rank them, best outcome first.

        Ranking is deterministic and rule-based: highest net customer
        benefit first, then fewest customers lost, then scenario id.
        """
        outcomes = tuple(self.simulate(scenario) for scenario in scenarios)
        ranked = tuple(
            sorted(
                outcomes,
                key=lambda outcome: (
                    -outcome.net_customer_delta,
                    outcome.lost_customer_count,
                    outcome.scenario_id,
                ),
            )
        )
        rationale = tuple(
            f"{outcome.scenario_id}: net customer delta "
            f"{outcome.net_customer_delta:+d} "
            f"(lost {outcome.lost_customer_count}, restored {outcome.restored_customer_count})"
            for outcome in ranked
        )
        return ScenarioComparison(
            comparison_id="comparison:" + ":".join(outcome.scenario_id for outcome in ranked),
            outcomes=ranked,
            ranking=tuple(outcome.scenario_id for outcome in ranked),
            rationale=rationale,
        )

    def replay(self, scenario: Scenario) -> ScenarioOutcome:
        """Re-run a scenario; identical inputs produce identical outcomes."""
        return self.simulate(scenario)

    def _overlay(self, scenario: Scenario) -> HypotheticalNetworkState:
        switchable = {edge.edge_id: edge.is_switchable for edge in self.view.topology.edges}
        sources = set(self.view.source_nodes())
        failed_edges: set[str] = set()
        opened: set[str] = set()
        closed: set[str] = set()
        failed_sources: set[str] = set()
        for action in scenario.actions:
            if action.kind in {"open_switch", "close_switch"}:
                if action.target_id not in switchable:
                    raise OperationalIntelligenceError(
                        f"unknown edge in scenario {scenario.scenario_id}: {action.target_id}"
                    )
                if not switchable[action.target_id]:
                    raise OperationalIntelligenceError(
                        f"scenario {scenario.scenario_id} operates "
                        f"non-switchable edge {action.target_id}"
                    )
                if action.kind == "open_switch":
                    opened.add(action.target_id)
                    closed.discard(action.target_id)
                else:
                    closed.add(action.target_id)
                    opened.discard(action.target_id)
            elif action.kind == "fail_edge":
                if action.target_id not in switchable:
                    raise OperationalIntelligenceError(
                        f"unknown edge in scenario {scenario.scenario_id}: {action.target_id}"
                    )
                failed_edges.add(action.target_id)
            else:
                if action.target_id not in sources:
                    raise OperationalIntelligenceError(
                        f"unknown source in scenario {scenario.scenario_id}: {action.target_id}"
                    )
                failed_sources.add(action.target_id)
        return HypotheticalNetworkState(
            self.view,
            failed_edges=frozenset(failed_edges),
            opened_edges=frozenset(opened),
            closed_edges=frozenset(closed),
            failed_sources=frozenset(failed_sources),
        )
