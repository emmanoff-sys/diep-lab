"""WP-010 OA-050 — non-destructive scenario simulation tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import fault_on_e1, operations_stack  # noqa: E402

from services.adms_operational_intelligence import (  # noqa: E402
    OperationalIntelligenceError,
    Scenario,
    ScenarioAction,
    ScenarioSimulationService,
)

ALL_NODES = ("a", "b", "c", "d", "e", "f1", "f2")


def _scenario(scenario_id: str, *actions: ScenarioAction) -> Scenario:
    return Scenario(scenario_id=scenario_id, description=scenario_id, actions=tuple(actions))


def test_planned_switching_scenario_reports_impact():
    view, _ = operations_stack()
    outcome = ScenarioSimulationService(view).simulate(
        _scenario("scenario:open-sw1", ScenarioAction("open_switch", "sw1"))
    )
    assert outcome.energized_before == ALL_NODES
    assert outcome.de_energized_nodes == ("b", "c")
    assert outcome.lost_load_kw == 100.0
    assert outcome.lost_customer_count == 40
    assert outcome.re_energized_nodes == ()


def test_equipment_outage_scenario():
    view, _ = operations_stack()
    outcome = ScenarioSimulationService(view).simulate(
        _scenario("scenario:fail-e1", ScenarioAction("fail_edge", "e1"))
    )
    assert outcome.de_energized_nodes == ("a", "b", "c")
    assert outcome.lost_customer_count == 40


def test_restoration_scenario_re_energises_dark_region():
    view, repository = operations_stack()
    fault_on_e1(repository)
    outcome = ScenarioSimulationService(view).simulate(
        _scenario("scenario:close-tie1", ScenarioAction("close_switch", "tie1"))
    )
    assert outcome.energized_before == ("d", "e", "f1", "f2")
    assert outcome.re_energized_nodes == ("a", "b", "c")
    assert outcome.restored_load_kw == 100.0
    assert outcome.restored_customer_count == 40
    by_feeder = {loading.feeder_id: loading for loading in outcome.feeder_loading}
    assert by_feeder["f2"].served_load_kw == 150.0
    assert by_feeder["f1"].served_load_kw == 0.0


def test_simulation_is_non_destructive():
    view, repository = operations_stack()
    service = ScenarioSimulationService(view)
    service.simulate(_scenario("scenario:open-sw1", ScenarioAction("open_switch", "sw1")))
    assert view.energized_nodes() == ALL_NODES
    assert repository.get_state("sw1", asset_kind="edge") is None


def test_last_action_wins_for_repeated_switch_operations():
    view, _ = operations_stack()
    outcome = ScenarioSimulationService(view).simulate(
        _scenario(
            "scenario:open-then-close",
            ScenarioAction("open_switch", "sw1"),
            ScenarioAction("close_switch", "sw1"),
        )
    )
    assert outcome.energized_after == ALL_NODES


def test_invalid_scenario_actions_raise():
    view, _ = operations_stack()
    service = ScenarioSimulationService(view)
    with pytest.raises(OperationalIntelligenceError):
        service.simulate(_scenario("scenario:bad", ScenarioAction("close_switch", "e2")))
    with pytest.raises(OperationalIntelligenceError):
        service.simulate(_scenario("scenario:bad", ScenarioAction("open_switch", "zz")))
    with pytest.raises(OperationalIntelligenceError):
        service.simulate(_scenario("scenario:bad", ScenarioAction("fail_source", "a")))


def test_comparison_ranks_scenarios_deterministically():
    view, _ = operations_stack()
    service = ScenarioSimulationService(view)
    comparison = service.compare(
        (
            _scenario("scenario:open-sw1", ScenarioAction("open_switch", "sw1")),
            _scenario("scenario:fail-e4", ScenarioAction("fail_edge", "e4")),
        )
    )
    assert comparison.ranking == ("scenario:fail-e4", "scenario:open-sw1")
    assert any("net customer delta" in line for line in comparison.rationale)


def test_replay_is_deterministic():
    view, repository = operations_stack()
    fault_on_e1(repository)
    service = ScenarioSimulationService(view)
    scenario = _scenario("scenario:close-tie1", ScenarioAction("close_switch", "tie1"))
    assert service.replay(scenario) == service.simulate(scenario)
