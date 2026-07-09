"""WP-013-02 OA-067 — operator experience integration tests.

Drives the full six-layer stack over HTTP: a WP-008 operational event
creates the fault, WP-009 detects it, WP-010 assesses it, and the
operator reads everything through the Operator API and workspace pages
— which must remain strictly read-only."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402
from _adms_operator_fixtures import HISTORY, auth_headers, authenticator  # noqa: E402

from fastapi.testclient import TestClient
from services.adms_operational_state import (  # noqa: E402
    OperationalEvent,
    OperationalEventProcessor,
    OperationalStateValidator,
    StateUpdateEngine,
)
from services.adms_operations import (  # noqa: E402
    OperationsAuditTrail,
    OperatorDecisionSupport,
    OutageDetectionService,
)
from services.adms_operator_api import OperatorViewService  # noqa: E402
from services.adms_operator_ui import create_operator_experience_app  # noqa: E402
from services.adms_topology_services import OutageImpactService  # noqa: E402


def _live_stack():
    """Fault arrives as a WP-008 event; WP-009 records a recommendation."""
    view, repository = operations_stack()
    validator = OperationalStateValidator(view.topology)
    processor = OperationalEventProcessor(StateUpdateEngine(repository, validator))
    result = processor.process(
        OperationalEvent(
            event_id="evt-e1-trip",
            event_type="breaker_operation",
            asset_id="e1",
            asset_kind="edge",
            sequence=1,
            observed_at="2026-07-09T11:58:00Z",
            actor="scada-sim",
            payload={"status": "open", "available": False},
        )
    )
    assert result.update_result.accepted is True
    audit = OperationsAuditTrail()
    group = OutageDetectionService(view).detect_all()[0]
    OperatorDecisionSupport(view, audit=audit).recommend(group, recorded_at="2026-07-09T12:00:00Z")
    views = OperatorViewService(view, state_repository=repository, audit=audit, history=HISTORY)
    return view, repository, views


def test_end_to_end_event_to_operator_screens():
    view, repository, views = _live_stack()
    client = TestClient(create_operator_experience_app(views, authenticator()))

    dashboard = client.get("/api/v1/dashboard", headers=auth_headers()).json()
    assert dashboard["data"]["platform"]["customers_affected"] == 40

    recommendations = client.get("/api/v1/recommendations", headers=auth_headers()).json()
    assert recommendations["data"][0]["strategies"][0]["tie_edge_id"] == "tie1"
    assert recommendations["data"][0]["fault_candidates"][0]["confidence"] == 1.0

    dashboard_page = client.get("/ui/dashboard", headers=auth_headers())
    assert dashboard_page.status_code == 200
    assert "Customers affected: 40" in dashboard_page.text

    recommendations_page = client.get("/ui/recommendations", headers=auth_headers())
    assert "close tie1" in recommendations_page.text

    history_page = client.get("/ui/history", headers=auth_headers())
    assert "recommendation_issued" in history_page.text

    explorer_page = client.get("/ui/network/b", headers=auth_headers())
    assert explorer_page.status_code == 200
    assert "Topology explorer: b" in explorer_page.text


def test_ui_routes_require_authentication():
    _, _, views = _live_stack()
    client = TestClient(create_operator_experience_app(views, authenticator()))
    for path in ("/ui/dashboard", "/ui/network", "/ui/recommendations", "/ui/history"):
        assert client.get(path).status_code == 401


def test_entire_application_is_read_only():
    _, _, views = _live_stack()
    app = create_operator_experience_app(views, authenticator())
    methods = {
        method for route in app.routes if hasattr(route, "methods") for method in route.methods
    }
    assert methods <= {"GET", "HEAD"}
    client = TestClient(app)
    assert client.post("/ui/dashboard", headers=auth_headers()).status_code == 405
    assert client.delete("/api/v1/recommendations", headers=auth_headers()).status_code == 405


def test_operator_reads_do_not_mutate_platform_state():
    view, repository, views = _live_stack()
    client = TestClient(create_operator_experience_app(views, authenticator()))
    history_before = repository.history("e1")
    audit_before = views.audit_history().record_count
    for path in (
        "/api/v1/dashboard",
        "/api/v1/network",
        "/api/v1/recommendations",
        "/api/v1/history",
        "/ui/dashboard",
        "/ui/recommendations",
        "/ui/history",
    ):
        assert client.get(path, headers=auth_headers()).status_code == 200
    assert repository.history("e1") == history_before
    assert views.audit_history().record_count == audit_before


def test_operator_experience_is_deterministic():
    _, _, views_a = _live_stack()
    _, _, views_b = _live_stack()
    client_a = TestClient(create_operator_experience_app(views_a, authenticator()))
    client_b = TestClient(create_operator_experience_app(views_b, authenticator()))
    for path in ("/api/v1/dashboard", "/api/v1/recommendations", "/api/v1/history"):
        assert (
            client_a.get(path, headers=auth_headers()).json()
            == client_b.get(path, headers=auth_headers()).json()
        )
    assert (
        client_a.get("/ui/dashboard", headers=auth_headers()).text
        == client_b.get("/ui/dashboard", headers=auth_headers()).text
    )


def test_lower_layers_unchanged_regression():
    view, repository, views = _live_stack()
    # WP-007 static outage impact still answers as before.
    impact = OutageImpactService(view.topology).analyze_edge_outage("e2")
    assert "c" in impact.affected_nodes
    # WP-009 detection and WP-008 history behave exactly as pre-WP-013-02.
    group = OutageDetectionService(view).detect_all()[0]
    assert group.affected_nodes == ("a", "b", "c")
    assert len(repository.history("e1")) == 1
