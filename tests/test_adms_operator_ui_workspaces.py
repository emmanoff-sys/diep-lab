"""WP-013-02 OA-063..066 — operator workspace page tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operator_fixtures import operator_stack  # noqa: E402

from services.adms_operator_ui import (  # noqa: E402
    render_dashboard,
    render_history,
    render_network,
    render_recommendations,
    render_topology_explorer,
)


def test_dashboard_page_shows_status_health_and_indicators():
    views, _, _ = operator_stack(faulted=True)
    page = render_dashboard(views.dashboard())
    assert page.active_item_id == "dashboard"
    assert "Customers affected: 40" in page.body
    assert "pill-attention" in page.body
    assert "outage-group:001" in page.body
    assert "operational-intelligence" in page.body


def test_dashboard_page_healthy_state():
    views, _, _ = operator_stack()
    page = render_dashboard(views.dashboard())
    assert "No active outages detected." in page.body
    assert "Customers affected: 0" in page.body


def test_network_page_lists_feeders_topology_and_states():
    views, _, _ = operator_stack(faulted=True)
    page = render_network(views.network_workspace())
    assert "Feeder status" in page.body
    assert "<td>f1</td>" in page.body and "<td>f2</td>" in page.body
    assert "<td>tie1</td>" in page.body
    assert "Operational state panels" in page.body


def test_network_page_search_results():
    views, _, _ = operator_stack()
    results = views.asset_search("tie")
    page = render_network(views.network_workspace(), search_query="tie", search_results=results)
    assert 'value="tie"' in page.body
    assert "<td>tie1</td>" in page.body
    assert 'method="get"' in page.body


def test_topology_explorer_page():
    views, _, _ = operator_stack(faulted=True)
    page = render_topology_explorer(views.topology_explorer("b"), views.asset_state_panel("b"))
    assert "Topology explorer: b" in page.body
    assert "<td>sw1</td>" in page.body
    assert "DE-ENERGISED" not in page.body.split("Neighbouring nodes")[0]
    assert "c (load, DE-ENERGISED)" in page.body


def test_recommendations_page_presents_strategy_explanations_and_rules():
    views, _, _ = operator_stack(faulted=True)
    page = render_recommendations(views.recommendations())
    assert "close tie1" in page.body
    assert "strategy:restore:tie1:f2" in page.body
    assert "Probable fault segments" in page.body
    assert "<td>e1</td>" in page.body
    assert "Rule evaluation" in page.body
    assert "<td>OI-R-001</td>" in page.body
    assert "Constraints" in page.body


def test_recommendations_page_with_no_outage():
    views, _, _ = operator_stack()
    page = render_recommendations(views.recommendations())
    assert "No active outages" in page.body


def test_history_page_lists_records_and_timeline():
    views, _, _ = operator_stack(faulted=True, seed_audit=True)
    page = render_history(views.audit_history(), views.timeline())
    assert "Audit history (3 record(s))" in page.body
    assert "recommendation_issued" in page.body
    assert '<ol class="timeline">' in page.body
    assert "decision-support" in page.body


def test_history_page_search_echo():
    views, _, _ = operator_stack(faulted=True, seed_audit=True)
    history = views.audit_history(text="plan")
    page = render_history(history, views.timeline(), search_text="plan")
    assert 'value="plan"' in page.body
    assert "Audit history (1 record(s))" in page.body


def test_workspace_pages_contain_no_mutating_forms():
    views, _, _ = operator_stack(faulted=True, seed_audit=True)
    pages = (
        render_dashboard(views.dashboard()),
        render_network(views.network_workspace()),
        render_recommendations(views.recommendations()),
        render_history(views.audit_history(), views.timeline()),
    )
    for page in pages:
        lowered = page.body.lower()
        assert 'method="post"' not in lowered
        assert '<input type="hidden"' not in lowered
