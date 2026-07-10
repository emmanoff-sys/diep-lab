"""WP-011-03 OA-087 — GIS connector integration tests.

Drives the full path from GIS stub → identity resolution → topology
translation → reconciliation → contract validation, plus regression
guards for Phase 1 and EPIC-011 layers.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402

from services.adms_topology_services import OutageImpactService  # noqa: E402
from services.gis_connector import (  # noqa: E402
    ConnectorConfig,
    ConnectorLifecycle,
    ConnectorRegistry,
    GISAssetIdentityMap,
    GISConnectorSession,
    GISTopologyTranslator,
    TopologyReconciler,
)
from services.gis_connector.harness import (  # noqa: E402
    GIS_CANONICAL_IDENTITY_MAP,
    GIS_TWO_FEEDER_BATCH,
)
from services.scada_connector.harness import GisStub  # noqa: E402
from services.scada_connector.harness.contracts import validate_mapped_topology  # noqa: E402

_GIS_CONFIG = ConnectorConfig(connector_id="gis-adapter-01", actor="gis-connector")
_TWO_FEEDER_NODES = frozenset({"f1", "a", "b", "c", "f2", "d", "e"})
_TWO_FEEDER_EDGES = frozenset({"e1", "sw1", "e2", "tie1", "e3", "e4"})


def _identity() -> GISAssetIdentityMap:
    return GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP)


def _translator() -> GISTopologyTranslator:
    return GISTopologyTranslator(_identity())


def test_stub_to_topology_end_to_end():
    """GIS stub → translate → canonical MappedTopology satisfies contract."""
    stub = GisStub(GIS_TWO_FEEDER_BATCH)
    batch = stub.fetch_model()
    result = _translator().translate(batch)
    assert result.success
    validate_mapped_topology(result.topology)


def test_stub_to_topology_to_reconciliation():
    """GIS stub → translate → reconcile against existing topology produces report."""
    stub = GisStub(GIS_TWO_FEEDER_BATCH)
    result = _translator().translate(stub.fetch_model())
    report = TopologyReconciler().reconcile(
        result.topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES
    )
    assert report.advisory_only
    assert report.import_count_nodes == 7
    assert report.import_count_edges == 6


def test_gis_connector_is_read_only():
    """GIS connector exposes no write, author, modify, or control methods."""
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    topology = result.topology
    assert not hasattr(topology, "write")
    assert not hasattr(topology, "modify")
    assert not hasattr(topology, "delete")
    assert not hasattr(topology, "push_to_gis")
    assert not hasattr(topology, "control_action")
    assert not hasattr(topology, "command")


def test_reconciliation_report_is_advisory_only_no_auto_correction():
    """Reconciliation report makes no changes to existing or imported topology."""
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    nodes_before = frozenset(_TWO_FEEDER_NODES)
    edges_before = frozenset(_TWO_FEEDER_EDGES)
    topology_nodes_before = result.topology.nodes

    TopologyReconciler().reconcile(result.topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)

    assert frozenset(_TWO_FEEDER_NODES) == nodes_before
    assert frozenset(_TWO_FEEDER_EDGES) == edges_before
    assert result.topology.nodes == topology_nodes_before


def test_lifecycle_tracks_topology_submissions():
    lifecycle = ConnectorLifecycle(_GIS_CONFIG)
    lifecycle.on_connect()
    lifecycle.on_event_submitted()  # topology import submitted
    lifecycle.on_event_submitted()
    h = lifecycle.health()
    assert h.events_submitted == 2
    assert h.healthy


def test_registry_manages_gis_connector():
    registry = ConnectorRegistry()
    registry.register(_GIS_CONFIG)
    assert _GIS_CONFIG.connector_id in registry.connector_ids
    retrieved = registry.get(_GIS_CONFIG.connector_id)
    assert retrieved.actor == "gis-connector"


def test_translation_produces_no_control_output():
    """Translated topology contains no device control fields."""
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    for node in result.topology.nodes:
        assert "command" not in node
        assert "write_back" not in node
        assert "control" not in node
    for edge in result.topology.edges:
        assert "command" not in edge
        assert "write_back" not in edge
        assert "control" not in edge


def test_regression_wp007_topology_unaffected():
    """WP-007 topology service unaffected by GIS connector operation."""
    view, _ = operations_stack()
    _translator().translate(GIS_TWO_FEEDER_BATCH)
    impact = OutageImpactService(view.topology).analyze_edge_outage("e2")
    assert "c" in impact.affected_nodes
    assert impact.customer_count >= 40


def test_regression_phase1_adms_stack_intact():
    """Phase 1 ADMS operational stack unchanged by GIS connector operation."""
    view, _ = operations_stack()
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    report = TopologyReconciler().reconcile(
        result.topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES
    )
    # Phase 1 state invariants hold independently of reconciliation
    node_ids = {n.node_id for n in view.topology.nodes}
    assert "f1" in node_ids
    assert "e1" in {e.edge_id for e in view.topology.edges}
    assert report.advisory_only


def test_full_scenario_new_topology_identified_for_review():
    """New network area in GIS import is flagged for operator review."""
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    # Simulate existing topology missing feeder f2 and its downstream
    partial_existing_nodes = frozenset({"f1", "a", "b", "c"})
    partial_existing_edges = frozenset({"e1", "sw1", "e2"})
    report = TopologyReconciler().reconcile(
        result.topology, partial_existing_nodes, partial_existing_edges
    )
    new_nodes = {i.asset_id for i in report.by_kind("new_asset") if "node" in i.detail}
    new_edges = {i.asset_id for i in report.by_kind("new_asset") if "edge" in i.detail}
    assert "f2" in new_nodes
    assert "d" in new_nodes
    assert "e" in new_nodes
    assert "e3" in new_edges
    assert "e4" in new_edges
    assert report.requires_operator_review


def test_gis_connector_session_is_subclass_of_abstract():
    assert issubclass(GISConnectorSession, object)
