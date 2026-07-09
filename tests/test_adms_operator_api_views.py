"""WP-013-02 OA-061/063..066 — operator view composition tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operator_fixtures import HISTORY, operator_stack  # noqa: E402

from services.adms_operational_intelligence import (  # noqa: E402
    OperationalIntelligenceService,
)
from services.adms_operations import OutageDetectionService  # noqa: E402
from services.adms_operator_api import UnknownAssetError  # noqa: E402


def test_dashboard_healthy_network():
    views, _, _ = operator_stack()
    dashboard = views.dashboard()
    assert dashboard.platform.node_count == 7
    assert dashboard.platform.edge_count == 6
    assert dashboard.platform.energized_node_count == 7
    assert dashboard.platform.active_outage_groups == 0
    assert dashboard.platform.customers_affected == 0
    assert all(item.status == "operational" for item in dashboard.services)
    by_id = {item.indicator_id: item for item in dashboard.indicators}
    assert by_id["customers-affected"].severity == "normal"
    # Fixture network has two genuinely unmitigable N-1 contingencies.
    assert by_id["n1-unmitigated"].value == "2"
    assert by_id["n1-unmitigated"].severity == "attention"


def test_dashboard_reports_active_outage():
    views, _, _ = operator_stack(faulted=True)
    dashboard = views.dashboard()
    assert dashboard.platform.active_outage_groups == 1
    assert dashboard.platform.customers_affected == 40
    outage = dashboard.active_outages[0]
    assert outage.affected_nodes == ("a", "b", "c")
    assert "e1" in outage.candidate_cause_edges
    by_id = {item.indicator_id: item for item in dashboard.indicators}
    assert by_id["customers-affected"].value == "40"
    assert by_id["customers-affected"].severity == "attention"
    assert by_id["energized-nodes"].value == "4/7"


def test_network_workspace_feeder_status():
    views, _, _ = operator_stack(faulted=True)
    workspace = views.network_workspace()
    by_feeder = {feeder.feeder_id: feeder for feeder in workspace.feeders}
    assert by_feeder["f1"].fully_energized is False
    assert by_feeder["f2"].fully_energized is True
    assert len(workspace.nodes) == 7
    assert len(workspace.edges) == 6
    e1 = next(edge for edge in workspace.edges if edge.edge_id == "e1")
    assert e1.available is False and e1.closed is False


def test_asset_search_matches_nodes_and_edges():
    views, _, _ = operator_stack()
    results = views.asset_search("tie")
    assert [result.asset_id for result in results] == ["tie1"]
    results = views.asset_search("load")
    assert {result.asset_id for result in results} == {"c", "e"}
    assert views.asset_search("") == ()
    assert views.asset_search("zzz") == ()


def test_asset_state_panel_edge_and_node():
    views, _, _ = operator_stack(faulted=True)
    panel = views.asset_state_panel("e1")
    assert panel.asset_kind == "edge"
    assert panel.available is False
    assert panel.history_count == 1
    assert panel.last_observed_at == "2026-07-08T10:01:00Z"
    node_panel = views.asset_state_panel("c")
    assert node_panel.asset_kind == "node"
    assert node_panel.energized is False
    with pytest.raises(UnknownAssetError):
        views.asset_state_panel("zz")


def test_topology_explorer_neighborhood():
    views, _, _ = operator_stack()
    neighborhood = views.topology_explorer("b")
    assert [edge.edge_id for edge in neighborhood.edges] == ["e2", "sw1", "tie1"]
    assert {node.node_id for node in neighborhood.neighbors} == {"a", "c", "d"}
    with pytest.raises(UnknownAssetError):
        views.topology_explorer("e1")  # an edge is not a node


def test_recommendations_have_no_duplicated_business_logic():
    """The workspace must present exactly what WP-009/010 computed."""
    views, _, _ = operator_stack(faulted=True)
    workspaces = views.recommendations()
    assert len(workspaces) == 1
    workspace = workspaces[0]

    group = OutageDetectionService(views.view).detect_all()[0]
    assessment = OperationalIntelligenceService(views.view, history=HISTORY).assess(group)
    top = workspace.strategies[0]
    source = assessment.strategies[0]
    assert top.strategy_id == source.strategy_id
    assert top.rank == source.rank
    assert top.max_feeder_load_kw == source.max_feeder_load_kw
    assert [step.edge_id for step in top.sequence] == [step.edge_id for step in source.sequence]
    assert workspace.fault_candidates[0].edge_id == assessment.fault_report.candidates[0].edge_id
    assert workspace.rule_outcomes[0].rule_id == assessment.rule_trace.outcomes[0].rule_id


def test_history_workspace_filters_and_search():
    views, _, audit = operator_stack(faulted=True, seed_audit=True)
    everything = views.audit_history()
    assert everything.record_count == 3
    only_recommendations = views.recommendation_history()
    assert only_recommendations.record_count == 1
    assert only_recommendations.records[0].kind == "recommendation_issued"
    by_actor = views.audit_history(actor="decision-support")
    assert by_actor.record_count == 3
    searched = views.audit_history(text="outage-group:001")
    assert searched.record_count == 3
    assert views.audit_history(text="no-such-thing").record_count == 0


def test_record_trace_and_unknown_record():
    views, _, _ = operator_stack(faulted=True, seed_audit=True)
    issued = views.recommendation_history().records[0]
    trace = views.record_trace(issued.record_id)
    assert [record.kind for record in trace] == [
        "outage_detected",
        "plan_generated",
        "recommendation_issued",
    ]
    with pytest.raises(UnknownAssetError):
        views.record_trace("decision:999999")


def test_timeline_merges_audit_and_state_history():
    views, _, _ = operator_stack(faulted=True, seed_audit=True)
    entries = views.timeline("e1")
    sources = [entry.source for entry in entries]
    assert "state" in sources
    state_entry = next(entry for entry in entries if entry.source == "state")
    assert state_entry.reference_id == "u-e1-fault"
    all_audit = views.timeline()
    assert len(all_audit) == 3
    assert [entry.occurred_at for entry in all_audit] == sorted(
        entry.occurred_at for entry in all_audit
    )


def test_views_are_deterministic():
    views_a, _, _ = operator_stack(faulted=True, seed_audit=True)
    views_b, _, _ = operator_stack(faulted=True, seed_audit=True)
    assert views_a.dashboard() == views_b.dashboard()
    assert views_a.network_workspace() == views_b.network_workspace()
    assert views_a.recommendations() == views_b.recommendations()
    assert views_a.audit_history() == views_b.audit_history()
