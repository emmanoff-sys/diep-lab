"""Operator workspaces for WP-013-02 (OA-063..OA-066).

Four read-only pages composed from Operator API view models through the
shared component library: situational awareness dashboard, network
operations, operational recommendations, and operational history. Pages
present existing platform intelligence — they compute nothing themselves.
"""

from __future__ import annotations

from services.adms_operator_api.models import (
    AssetStatePanel,
    DashboardView,
    HistoryWorkspaceView,
    NetworkWorkspaceView,
    RecommendationWorkspaceView,
    TimelineEntryView,
    TopologyNeighborhood,
)

from .components import (
    BulletList,
    Card,
    KeyValueList,
    SearchForm,
    StatusPill,
    Table,
    Timeline,
    join,
)
from .framework import Navigation, NavigationItem, Page, Route, Router

NAVIGATION = Navigation(
    items=(
        NavigationItem("dashboard", "Dashboard", "/ui/dashboard"),
        NavigationItem("network", "Network Operations", "/ui/network"),
        NavigationItem("recommendations", "Recommendations", "/ui/recommendations"),
        NavigationItem("history", "History", "/ui/history"),
    )
)


def build_router() -> Router:
    router = Router()
    router.register(Route("dashboard", "/ui/dashboard", "Situational Awareness"))
    router.register(Route("network", "/ui/network", "Network Operations"))
    router.register(Route("recommendations", "/ui/recommendations", "Recommendations"))
    router.register(Route("history", "/ui/history", "Operational History"))
    return router


# --- OA-063: situational awareness dashboard --------------------------------------
def render_dashboard(view: DashboardView) -> Page:
    platform = view.platform
    status_card = Card(
        title="Platform status",
        body=KeyValueList(
            pairs=(
                ("Nodes", str(platform.node_count)),
                ("Edges", str(platform.edge_count)),
                ("Energised nodes", f"{platform.energized_node_count}/{platform.node_count}"),
                ("Feeders", str(platform.feeder_count)),
                ("Active outage groups", str(platform.active_outage_groups)),
                ("Customers affected", str(platform.customers_affected)),
            )
        ).render(),
    )
    health_card = Card(
        title="Service health",
        body=Table(
            headers=("Service", "Status", "Detail"),
            rows=tuple((item.name, item.status, item.detail) for item in view.services),
        ).render(),
    )
    indicator_pills = join(
        [
            StatusPill(
                label=f"{indicator.label}: {indicator.value}",
                tone="ok" if indicator.severity == "normal" else "attention",
            )
            for indicator in view.indicators
        ]
    )
    outages_card = Card(
        title="Active operational summaries",
        body=(
            Table(
                headers=("Group", "Feeders", "Nodes affected", "Customers", "Candidate causes"),
                rows=tuple(
                    (
                        outage.group_id,
                        ", ".join(outage.feeder_ids),
                        str(len(outage.affected_nodes)),
                        str(outage.customer_count),
                        ", ".join(outage.candidate_cause_edges),
                    )
                    for outage in view.active_outages
                ),
            ).render()
            if view.active_outages
            else "<p>No active outages detected.</p>"
        ),
    )
    body = f'<div class="indicators">{indicator_pills}</div>' + join(
        [status_card, health_card, outages_card]
    )
    return Page(title="Situational Awareness", active_item_id="dashboard", body=body)


# --- OA-064: network operations workspace ------------------------------------------
def render_network(
    view: NetworkWorkspaceView,
    *,
    search_query: str = "",
    search_results: tuple = (),
) -> Page:
    feeder_card = Card(
        title="Feeder status",
        body=Table(
            headers=(
                "Feeder",
                "Healthy",
                "Energised nodes",
                "De-energised nodes",
                "Fully energised",
            ),
            rows=tuple(
                (
                    feeder.feeder_id,
                    "yes" if feeder.healthy else "NO",
                    str(feeder.energized_node_count),
                    str(feeder.deenergized_node_count),
                    "yes" if feeder.fully_energized else "NO",
                )
                for feeder in view.feeders
            ),
        ).render(),
    )
    topology_card = Card(
        title="Network topology",
        body=Table(
            headers=("Edge", "Type", "From", "To", "Switchable", "Closed", "Available"),
            rows=tuple(
                (
                    edge.edge_id,
                    edge.edge_type,
                    edge.from_node,
                    edge.to_node,
                    "yes" if edge.switchable else "no",
                    "closed" if edge.closed else "open",
                    "yes" if edge.available else "NO",
                )
                for edge in view.edges
            ),
        ).render(),
    )
    nodes_card = Card(
        title="Operational state panels",
        body=Table(
            headers=("Node", "Type", "Energised", "Available"),
            rows=tuple(
                (
                    node.node_id,
                    node.node_type,
                    "yes" if node.energized else "NO",
                    "yes" if node.available else "NO",
                )
                for node in view.nodes
            ),
        ).render(),
    )
    search_body = SearchForm(
        action="/ui/network", query_param="q", placeholder="Search assets", value=search_query
    ).render()
    if search_query:
        search_body += Table(
            headers=("Asset", "Kind", "Label"),
            rows=tuple((result.asset_id, result.kind, result.label) for result in search_results),
        ).render()
    search_card = Card(title="Asset search", body=search_body)
    body = join([feeder_card, search_card, topology_card, nodes_card])
    return Page(title="Network Operations", active_item_id="network", body=body)


def render_topology_explorer(view: TopologyNeighborhood, panel: AssetStatePanel) -> Page:
    node_card = Card(
        title=f"Topology explorer: {view.node_id}",
        body=KeyValueList(
            pairs=(
                ("Type", view.node.node_type),
                ("Energised", "yes" if view.node.energized else "NO"),
                ("Available", "yes" if view.node.available else "NO"),
                ("State history entries", str(panel.history_count)),
                ("Last observed", panel.last_observed_at or "never"),
            )
        ).render(),
    )
    edges_card = Card(
        title="Connected edges",
        body=Table(
            headers=("Edge", "Type", "From", "To", "Closed", "Available"),
            rows=tuple(
                (
                    edge.edge_id,
                    edge.edge_type,
                    edge.from_node,
                    edge.to_node,
                    "closed" if edge.closed else "open",
                    "yes" if edge.available else "NO",
                )
                for edge in view.edges
            ),
        ).render(),
    )
    neighbors_card = Card(
        title="Neighbouring nodes",
        body=BulletList(
            items=tuple(
                f"{neighbor.node_id} ({neighbor.node_type}, "
                f"{'energised' if neighbor.energized else 'DE-ENERGISED'})"
                for neighbor in view.neighbors
            )
        ).render(),
    )
    return Page(
        title=f"Topology Explorer — {view.node_id}",
        active_item_id="network",
        body=join([node_card, edges_card, neighbors_card]),
    )


# --- OA-065: operational recommendations workspace ---------------------------------
def render_recommendations(views: tuple[RecommendationWorkspaceView, ...]) -> Page:
    if not views:
        body = "<p>No active outages — no recommendations required.</p>"
        return Page(title="Recommendations", active_item_id="recommendations", body=body)
    sections = []
    for workspace in views:
        outage_card = Card(
            title=f"Outage summary: {workspace.group_id}",
            body=KeyValueList(
                pairs=(
                    ("Feeders", ", ".join(workspace.outage.feeder_ids)),
                    ("Affected nodes", ", ".join(workspace.outage.affected_nodes)),
                    ("Customers", str(workspace.outage.customer_count)),
                    ("Candidate causes", ", ".join(workspace.outage.candidate_cause_edges)),
                )
            ).render(),
        )
        fault_card = Card(
            title="Probable fault segments",
            body=Table(
                headers=("Segment", "Confidence", "Evidence"),
                rows=tuple(
                    (
                        candidate.edge_id,
                        f"{candidate.confidence:.2f}",
                        "; ".join(candidate.evidence),
                    )
                    for candidate in workspace.fault_candidates
                ),
            ).render(),
        )
        strategy_rows = tuple(
            (
                str(strategy.rank),
                strategy.strategy_id,
                " then ".join(f"{step.action} {step.edge_id}" for step in strategy.sequence),
                "safe" if strategy.safe else "NOT SAFE",
                "yes" if strategy.capacity_ok else "NO",
                str(strategy.restored_customer_count),
                f"{strategy.max_feeder_load_kw:g} kW",
            )
            for strategy in workspace.strategies
        )
        strategies_card = Card(
            title="Switching recommendations and restoration strategies",
            body=(
                Table(
                    headers=(
                        "Rank",
                        "Strategy",
                        "Sequence",
                        "Safety",
                        "Capacity OK",
                        "Customers restored",
                        "Peak feeder load",
                    ),
                    rows=strategy_rows,
                ).render()
                if strategy_rows
                else "<p>No restoration strategy is currently available.</p>"
            ),
        )
        explanation_sections = []
        for explanation in workspace.explanations:
            pairs = [("Summary", explanation.summary)]
            explanation_sections.append(
                Card(
                    title=f"Explanation: {explanation.subject_id}",
                    body=KeyValueList(pairs=tuple(pairs)).render()
                    + BulletList(items=explanation.rationale).render()
                    + (
                        "<h4>Evidence</h4>" + BulletList(items=explanation.evidence).render()
                        if explanation.evidence
                        else ""
                    )
                    + (
                        "<h4>Constraints</h4>" + BulletList(items=explanation.constraints).render()
                        if explanation.constraints
                        else ""
                    ),
                )
            )
        rules_card = Card(
            title="Rule evaluation",
            body=Table(
                headers=("Rule", "Category", "Result", "Detail"),
                rows=tuple(
                    (
                        outcome.rule_id,
                        outcome.category,
                        "pass" if outcome.passed else "FAIL",
                        outcome.detail,
                    )
                    for outcome in workspace.rule_outcomes
                ),
            ).render(),
        )
        sections.append(
            join([outage_card, fault_card, strategies_card, *explanation_sections, rules_card])
        )
    return Page(
        title="Recommendations",
        active_item_id="recommendations",
        body="".join(sections),
    )


# --- OA-066: operational history workspace ------------------------------------------
def render_history(
    view: HistoryWorkspaceView,
    timeline: tuple[TimelineEntryView, ...],
    *,
    search_text: str = "",
) -> Page:
    search_card = Card(
        title="Search history",
        body=SearchForm(
            action="/ui/history",
            query_param="text",
            placeholder="Search audit records",
            value=search_text,
        ).render(),
    )
    records_card = Card(
        title=f"Audit history ({view.record_count} record(s))",
        body=Table(
            headers=("Record", "Seq", "Recorded", "Kind", "Subject", "Actor", "Summary"),
            rows=tuple(
                (
                    record.record_id,
                    str(record.sequence),
                    record.recorded_at,
                    record.kind,
                    record.subject_id,
                    record.actor,
                    record.summary,
                )
                for record in view.records
            ),
        ).render(),
    )
    timeline_card = Card(
        title="Event timeline",
        body=Timeline(
            entries=tuple((entry.occurred_at, entry.description) for entry in timeline)
        ).render(),
    )
    return Page(
        title="Operational History",
        active_item_id="history",
        body=join([search_card, records_card, timeline_card]),
    )
