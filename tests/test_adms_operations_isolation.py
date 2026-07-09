"""WP-009 OA-038 — isolation boundary analysis tests."""

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

from services.adms_operations import IsolationBoundaryService  # noqa: E402

REGION = ("a", "b", "c")


def test_boundary_points_are_the_region_crossings():
    view, repository = operations_stack()
    fault_on_e1(repository)
    points = IsolationBoundaryService(view).discover_isolation_points(REGION)
    assert [point.edge_id for point in points] == ["e1", "tie1"]
    by_id = {point.edge_id: point for point in points}
    assert by_id["e1"].switchable is False
    assert by_id["e1"].closed is False  # faulted open
    assert by_id["e1"].available is False
    assert by_id["tie1"].switchable is True
    assert by_id["tie1"].closed is False
    assert by_id["tie1"].available is True


def test_safe_candidates_require_operability():
    view, repository = operations_stack()
    fault_on_e1(repository)
    service = IsolationBoundaryService(view)
    points = service.discover_isolation_points(REGION)
    safe = service.safe_isolation_candidates(points)
    assert [point.edge_id for point in safe] == ["tie1"]


def test_unavailable_switch_excluded_from_safe_candidates():
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
    service = IsolationBoundaryService(view)
    boundary = service.analyze("outage-group:001", REGION)
    assert boundary.safe_isolation_edges == ()
    assert any("tie1" in diagnostic for diagnostic in boundary.diagnostics)


def test_verified_boundary_for_faulted_region():
    view, repository = operations_stack()
    fault_on_e1(repository)
    boundary = IsolationBoundaryService(view).analyze("outage-group:001", REGION)
    assert boundary.verified is True
    assert boundary.unisolated_nodes == ()
    assert boundary.safe_isolation_edges == ("tie1",)
    assert any("e1 is not switchable" in diagnostic for diagnostic in boundary.diagnostics)


def test_boundary_not_verified_when_supply_cannot_be_broken():
    """Region {b, c} while sw1 stays closed and conducting: opening only the
    operable boundary (sw1 IS operable here) isolates; but a region behind a
    NON-switchable conducting edge cannot be verified."""
    view, repository = operations_stack()
    # Region {c} is fed through non-switchable conducting e2 — no operable
    # boundary point exists, so simulated isolation leaves c energised.
    boundary = IsolationBoundaryService(view).analyze("subject:c", ("c",))
    assert boundary.safe_isolation_edges == ()
    assert boundary.verified is False
    assert boundary.unisolated_nodes == ("c",)
    assert any("conducting boundary edges" in d for d in boundary.diagnostics)


def test_operable_closed_boundary_verifies_by_opening():
    """De-energised region behind a closed switch: sw1 open isolates {b, c}."""
    view, repository = operations_stack()
    # Simulate upstream fault so the region is dark but sw1 remains closed.
    fault_on_e1(repository)
    boundary = IsolationBoundaryService(view).analyze("subject:bc", ("b", "c"))
    # Crossings: sw1 (a|b) and e2? e2 is inside. tie1 (b|d) crosses.
    assert boundary.safe_isolation_edges == ("sw1", "tie1")
    assert boundary.verified is True
