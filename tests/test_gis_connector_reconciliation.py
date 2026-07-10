"""WP-011-03 OA-085 — topology reconciliation tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.gis_connector import (  # noqa: E402
    GISAssetIdentityMap,
    GISTopologyTranslator,
    TopologyReconciler,
)
from services.gis_connector.harness import (  # noqa: E402
    GIS_CANONICAL_IDENTITY_MAP,
    GIS_TWO_FEEDER_BATCH,
)

_TWO_FEEDER_NODES = frozenset({"f1", "a", "b", "c", "f2", "d", "e"})
_TWO_FEEDER_EDGES = frozenset({"e1", "sw1", "e2", "tie1", "e3", "e4"})


def _translated_topology():
    translator = GISTopologyTranslator(GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP))
    return translator.translate(GIS_TWO_FEEDER_BATCH).topology


def test_reconcile_identical_topology_produces_no_items():
    topology = _translated_topology()
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)
    assert len(report.items) == 0


def test_report_advisory_only_is_always_true():
    topology = _translated_topology()
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)
    assert report.advisory_only is True


def test_new_node_detected_when_absent_from_existing():
    topology = _translated_topology()
    existing_nodes = _TWO_FEEDER_NODES - {"a"}  # pretend 'a' is new
    report = TopologyReconciler().reconcile(topology, existing_nodes, _TWO_FEEDER_EDGES)
    new = report.by_kind("new_asset")
    assert any(item.asset_id == "a" for item in new)


def test_new_edge_detected_when_absent_from_existing():
    topology = _translated_topology()
    existing_edges = _TWO_FEEDER_EDGES - {"e1"}  # pretend 'e1' is new
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, existing_edges)
    new = report.by_kind("new_asset")
    assert any(item.asset_id == "e1" for item in new)


def test_missing_node_detected_when_absent_from_import():
    topology = _translated_topology()
    extra_existing = _TWO_FEEDER_NODES | {"phantom-node"}
    report = TopologyReconciler().reconcile(topology, extra_existing, _TWO_FEEDER_EDGES)
    missing = report.by_kind("missing_asset")
    assert any(item.asset_id == "phantom-node" for item in missing)


def test_missing_edge_detected_when_absent_from_import():
    topology = _translated_topology()
    extra_existing = _TWO_FEEDER_EDGES | {"phantom-edge"}
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, extra_existing)
    missing = report.by_kind("missing_asset")
    assert any(item.asset_id == "phantom-edge" for item in missing)


def test_duplicate_node_id_detected():
    topology = _translated_topology()
    # Inject a duplicate node dict
    dup_node = dict(topology.nodes[0])
    from services.adms_topology_import.mapping import MappedTopology

    dup_topology = MappedTopology(
        source_system=topology.source_system,
        external_model_id=topology.external_model_id,
        external_model_version=topology.external_model_version,
        nodes=topology.nodes + (dup_node,),
        edges=topology.edges,
    )
    report = TopologyReconciler().reconcile(dup_topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)
    dups = report.by_kind("duplicate_id")
    assert len(dups) >= 1


def test_operator_review_item_added_when_new_assets_present():
    topology = _translated_topology()
    existing_nodes = _TWO_FEEDER_NODES - {"a", "b"}  # two new nodes
    report = TopologyReconciler().reconcile(topology, existing_nodes, _TWO_FEEDER_EDGES)
    assert report.requires_operator_review
    review = report.by_kind("operator_review")
    assert len(review) >= 1
    assert "2 new asset" in review[0].detail


def test_no_operator_review_when_no_new_assets():
    topology = _translated_topology()
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)
    assert not report.requires_operator_review


def test_report_counts_match_inputs():
    topology = _translated_topology()
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)
    assert report.import_count_nodes == 7
    assert report.import_count_edges == 6
    assert report.existing_count_nodes == len(_TWO_FEEDER_NODES)
    assert report.existing_count_edges == len(_TWO_FEEDER_EDGES)


def test_by_kind_filters_correctly():
    topology = _translated_topology()
    existing_nodes = _TWO_FEEDER_NODES - {"a"}
    report = TopologyReconciler().reconcile(topology, existing_nodes, _TWO_FEEDER_EDGES)
    new_items = report.by_kind("new_asset")
    missing_items = report.by_kind("missing_asset")
    assert all(i.kind == "new_asset" for i in new_items)
    assert all(i.kind == "missing_asset" for i in missing_items)


def test_report_model_id_and_version_from_topology():
    topology = _translated_topology()
    report = TopologyReconciler().reconcile(topology, _TWO_FEEDER_NODES, _TWO_FEEDER_EDGES)
    assert report.model_id == topology.external_model_id
    assert report.model_version == topology.external_model_version


def test_reconcile_empty_existing_all_new():
    topology = _translated_topology()
    report = TopologyReconciler().reconcile(topology, frozenset(), frozenset())
    new_nodes = {i.asset_id for i in report.by_kind("new_asset") if "node" in i.detail}
    new_edges = {i.asset_id for i in report.by_kind("new_asset") if "edge" in i.detail}
    assert new_nodes == _TWO_FEEDER_NODES
    assert new_edges == _TWO_FEEDER_EDGES
    assert report.requires_operator_review
