"""WP-010 OA-047 — restoration optimisation tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import (  # noqa: E402
    apply_update,
    fault_on_e1,
    operations_stack,
)

from services.adms_operational_intelligence import (  # noqa: E402
    RestorationOptimisationService,
)
from services.adms_operations import IsolationBoundary, IsolationBoundaryService  # noqa: E402


def _boundary(view, subject, region):
    return IsolationBoundaryService(view).analyze(subject, region)


def test_single_strategy_after_upstream_fault():
    view, repository = operations_stack()
    fault_on_e1(repository)
    region = ("a", "b", "c")
    strategies = RestorationOptimisationService(view).strategies(
        region, _boundary(view, "outage-group:001", region)
    )
    assert len(strategies) == 1
    strategy = strategies[0]
    assert strategy.strategy_id == "strategy:restore:tie1:f2"
    assert strategy.rank == 1
    assert strategy.safe is True
    assert strategy.capacity_ok is True
    assert [(step.action, step.edge_id) for step in strategy.sequence] == [("close", "tie1")]
    assert strategy.switch_operation_count == 1
    assert strategy.max_feeder_load_kw == 150.0


def test_sequence_orders_isolation_before_restoration():
    view, repository = operations_stack()
    fault_on_e1(repository)
    region = ("b", "c")
    strategies = RestorationOptimisationService(view).strategies(
        region, _boundary(view, "subject:bc", region)
    )
    strategy = strategies[0]
    assert [(step.action, step.edge_id, step.purpose) for step in strategy.sequence] == [
        ("open", "sw1", "isolate"),
        ("close", "tie1", "restore"),
    ]
    assert [step.step_number for step in strategy.sequence] == [1, 2]
    assert strategy.switch_operation_count == 2


def test_feeder_balancing_prefers_lower_post_restoration_peak():
    """With {b, c} dark behind an operator-opened sw1, re-closing sw1 keeps
    the feeders balanced (f1: 100 kW, f2: 50 kW) while tie1 would push f2
    to 150 kW — the balanced strategy must rank first."""
    view, repository = operations_stack()
    apply_update(
        repository,
        update_id="u-sw1-open",
        asset_id="sw1",
        asset_kind="edge",
        sequence=1,
        switch_status="open",
    )
    region = ("b", "c")
    strategies = RestorationOptimisationService(view).strategies(
        region, _boundary(view, "subject:bc", region)
    )
    assert [strategy.strategy_id for strategy in strategies] == [
        "strategy:restore:sw1:f1",
        "strategy:restore:tie1:f2",
    ]
    assert [strategy.rank for strategy in strategies] == [1, 2]
    assert strategies[0].max_feeder_load_kw == 100.0
    assert strategies[1].max_feeder_load_kw == 150.0


def test_unsafe_strategies_rank_last_and_are_flagged():
    view, repository = operations_stack()
    fault_on_e1(repository)
    region = ("a", "b", "c")
    verified = _boundary(view, "outage-group:001", region)
    unverified = IsolationBoundary(
        subject_id=verified.subject_id,
        isolation_points=verified.isolation_points,
        safe_isolation_edges=verified.safe_isolation_edges,
        verified=False,
        unisolated_nodes=("a",),
        diagnostics=verified.diagnostics,
    )
    strategies = RestorationOptimisationService(view).strategies(region, unverified)
    assert len(strategies) == 1
    assert strategies[0].safe is False
    assert strategies[0].rank == 1


def test_no_strategies_when_tie_unavailable():
    view, repository = operations_stack()
    fault_on_e1(repository)
    apply_update(
        repository,
        update_id="u-tie1-unavailable",
        asset_id="tie1",
        asset_kind="edge",
        sequence=2,
        available=False,
    )
    region = ("a", "b", "c")
    strategies = RestorationOptimisationService(view).strategies(
        region, _boundary(view, "outage-group:001", region)
    )
    assert strategies == ()


def test_optimisation_is_repeatable():
    view, repository = operations_stack()
    fault_on_e1(repository)
    region = ("a", "b", "c")
    service = RestorationOptimisationService(view)
    boundary = _boundary(view, "outage-group:001", region)
    assert service.strategies(region, boundary) == service.strategies(region, boundary)
