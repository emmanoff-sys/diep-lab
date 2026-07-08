"""WP-007 ADMS topology service foundation tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import MappedTopology  # noqa: E402
from services.adms_topology_services import (  # noqa: E402
    ConnectivityGraph,
    ElectricalPathAnalysisService,
    FeederTracingService,
    InMemoryTopologyRepository,
    NetworkQueryService,
    OutageImpactService,
    SwitchingSimulationService,
    TopologyRepositoryError,
)


def _node(node_id: str, node_type: str, *, customers: int | None = None) -> dict:
    metadata = {}
    if customers is not None:
        metadata["customer_count"] = customers
    return {
        "node_id": node_id,
        "node_type": node_type,
        "name": node_id,
        "latitude": 9.0,
        "longitude": 7.0,
        "nominal_kv": 11.0,
        "phases": "ABC",
        "attrs": {"external_id": node_id.replace("adms:node:", ""), "metadata": metadata},
    }


def _edge(
    edge_id: str,
    from_node: str,
    to_node: str,
    *,
    edge_type: str = "line",
    switchable: bool = False,
    closed: bool = True,
) -> dict:
    return {
        "edge_id": edge_id,
        "from_node": from_node,
        "to_node": to_node,
        "edge_type": edge_type,
        "is_switchable": switchable,
        "normally_closed": closed,
        "is_closed": closed,
        "rating_kw": 1500.0,
        "phases": "ABC",
        "attrs": {"external_id": edge_id.replace("adms:edge:", ""), "metadata": {}},
    }


def _repository() -> InMemoryTopologyRepository:
    mapped = MappedTopology(
        source_system="adms-supplier-a",
        external_model_id="model-wp-007",
        external_model_version="2026.07.08",
        nodes=(
            _node("adms:node:f1", "feeder"),
            _node("adms:node:f2", "feeder"),
            _node("adms:node:a", "bus"),
            _node("adms:node:b", "bus"),
            _node("adms:node:c", "load", customers=12),
            _node("adms:node:d", "meter"),
        ),
        edges=(
            _edge("adms:edge:e1", "adms:node:f1", "adms:node:a"),
            _edge(
                "adms:edge:sw1",
                "adms:node:a",
                "adms:node:b",
                edge_type="switch",
                switchable=True,
            ),
            _edge("adms:edge:e2", "adms:node:b", "adms:node:c"),
            _edge("adms:edge:e3", "adms:node:b", "adms:node:d"),
            _edge(
                "adms:edge:tie1",
                "adms:node:f2",
                "adms:node:b",
                edge_type="tie",
                switchable=True,
                closed=False,
            ),
            _edge(
                "adms:edge:loop1",
                "adms:node:a",
                "adms:node:c",
                edge_type="tie",
                switchable=True,
                closed=False,
            ),
        ),
    )
    return InMemoryTopologyRepository.from_mapped_topology(mapped)


def test_repository_indexes_mapped_topology_without_runtime_coupling():
    repository = _repository()

    assert repository.snapshot.source_system == "adms-supplier-a"
    assert repository.require_node("adms:node:c").metadata["customer_count"] == 12
    assert repository.find_node_by_external_id("c").node_id == "adms:node:c"
    assert repository.find_edge_by_external_id("sw1").edge_id == "adms:edge:sw1"
    assert [node.node_id for node in repository.nodes_by_type("feeder")] == [
        "adms:node:f1",
        "adms:node:f2",
    ]


def test_connectivity_graph_traverses_closed_edges_and_can_include_open_edges():
    graph = ConnectivityGraph(_repository())

    assert graph.reachable_from("adms:node:f1") == (
        "adms:node:a",
        "adms:node:b",
        "adms:node:c",
        "adms:node:d",
        "adms:node:f1",
    )
    assert "adms:node:f2" in graph.reachable_from("adms:node:f1", include_open=True)
    assert graph.shortest_path("adms:node:f1", "adms:node:c").edges == (
        "adms:edge:e1",
        "adms:edge:sw1",
        "adms:edge:e2",
    )


def test_query_service_returns_assets_and_relationships():
    service = NetworkQueryService(_repository())

    connected = service.connected_assets("adms:node:b")

    assert [asset.node.node_id for asset in connected] == [
        "adms:node:a",
        "adms:node:c",
        "adms:node:d",
    ]
    assert service.edges_by_type("switch")[0].edge_id == "adms:edge:sw1"


def test_feeder_tracing_returns_downstream_assets_and_upstream_path():
    service = FeederTracingService(_repository())

    trace = service.trace_downstream("adms:node:f1")

    assert trace.nodes == (
        "adms:node:a",
        "adms:node:b",
        "adms:node:c",
        "adms:node:d",
        "adms:node:f1",
    )
    assert service.feeder_for_node("adms:node:c") == "adms:node:f1"
    assert service.upstream_path("adms:node:c").nodes == (
        "adms:node:f1",
        "adms:node:a",
        "adms:node:b",
        "adms:node:c",
    )


def test_path_analysis_reports_primary_path_and_no_loop_in_radial_state():
    analysis = ElectricalPathAnalysisService(_repository()).analyze_path(
        "adms:node:f1",
        "adms:node:d",
    )

    assert analysis.primary_path.nodes == (
        "adms:node:f1",
        "adms:node:a",
        "adms:node:b",
        "adms:node:d",
    )
    assert analysis.alternate_paths == ()
    assert analysis.loop_detected is False


def test_outage_impact_identifies_downstream_assets_boundaries_and_customers():
    impact = OutageImpactService(_repository()).analyze_edge_outage("adms:edge:sw1")

    assert impact.affected_nodes == ("adms:node:b", "adms:node:c", "adms:node:d")
    assert impact.isolation_boundaries == (
        "adms:edge:loop1",
        "adms:edge:sw1",
        "adms:edge:tie1",
    )
    assert impact.customer_count == 13


def test_switching_simulation_opens_switch_without_mutating_original_repository():
    repository = _repository()
    result = SwitchingSimulationService(repository).simulate_switch("adms:edge:sw1", close=False)

    assert result.accepted is True
    assert result.affected_nodes == ("adms:node:b", "adms:node:c", "adms:node:d")
    assert repository.require_edge("adms:edge:sw1").is_closed is True
    assert result.repository.require_edge("adms:edge:sw1").is_closed is False


def test_switching_simulation_rejects_non_switchable_and_loop_creating_operations():
    service = SwitchingSimulationService(_repository())

    with pytest.raises(TopologyRepositoryError):
        service.simulate_switch("adms:edge:e2", close=False)

    loop_result = service.simulate_switch("adms:edge:loop1", close=True)

    assert loop_result.accepted is False
    assert loop_result.reason == "closing_switch_would_create_loop"
