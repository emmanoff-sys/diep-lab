"""WP-011-03 OA-083 — canonical topology translation tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.gis_connector import (  # noqa: E402
    GISAssetIdentityMap,
    GISEdgeFeature,
    GISNodeFeature,
    GISTopologyBatch,
    GISTopologyTranslator,
)
from services.gis_connector.harness import (  # noqa: E402
    GIS_CANONICAL_IDENTITY_MAP,
    GIS_TWO_FEEDER_BATCH,
)
from services.scada_connector.harness.contracts import validate_mapped_topology  # noqa: E402


def _translator() -> GISTopologyTranslator:
    return GISTopologyTranslator(GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP))


def test_full_translation_succeeds():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    assert result.success
    assert result.topology is not None
    assert result.translated_nodes == 7
    assert result.translated_edges == 6
    assert result.total_features == 13
    assert len(result.rejections) == 0


def test_translated_topology_satisfies_mapped_topology_contract():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    validate_mapped_topology(result.topology)


def test_translated_topology_node_ids_match_canonical():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    node_ids = {n["node_id"] for n in result.topology.nodes}
    assert node_ids == {"f1", "a", "b", "c", "f2", "d", "e"}


def test_translated_topology_edge_ids_match_canonical():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    edge_ids = {e["edge_id"] for e in result.topology.edges}
    assert edge_ids == {"e1", "sw1", "e2", "tie1", "e3", "e4"}


def test_gis_feeder_feature_class_maps_to_canonical_feeder():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    feeder_nodes = [n for n in result.topology.nodes if n["node_type"] == "feeder"]
    assert len(feeder_nodes) == 2
    assert {n["node_id"] for n in feeder_nodes} == {"f1", "f2"}


def test_gis_busbar_maps_to_canonical_bus():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    bus_nodes = [n for n in result.topology.nodes if n["node_type"] == "bus"]
    assert {n["node_id"] for n in bus_nodes} == {"a", "b", "d"}


def test_gis_load_point_maps_to_canonical_load():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    load_nodes = [n for n in result.topology.nodes if n["node_type"] == "load"]
    assert {n["node_id"] for n in load_nodes} == {"c", "e"}


def test_gis_disconnector_maps_to_canonical_switch():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    sw1 = next(e for e in result.topology.edges if e["edge_id"] == "sw1")
    assert sw1["edge_type"] == "switch"
    assert sw1["is_switchable"] is True


def test_gis_overhead_line_maps_to_canonical_line():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    e1 = next(e for e in result.topology.edges if e["edge_id"] == "e1")
    assert e1["edge_type"] == "line"


def test_tie_switch_is_normally_open():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    tie1 = next(e for e in result.topology.edges if e["edge_id"] == "tie1")
    assert tie1["is_switchable"] is True
    assert tie1["normally_closed"] is False
    assert tie1["is_closed"] is False


def test_topology_source_metadata_preserved():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    assert result.topology.source_system == GIS_TWO_FEEDER_BATCH.source_system
    assert result.topology.external_model_id == GIS_TWO_FEEDER_BATCH.model_id
    assert result.topology.external_model_version == GIS_TWO_FEEDER_BATCH.model_version


def test_node_attrs_record_gis_source():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    f1 = next(n for n in result.topology.nodes if n["node_id"] == "f1")
    assert f1["attrs"]["source"] == "gis"
    assert f1["attrs"]["external_id"] == "GIS-NODE-F1"


def test_edge_attrs_record_gis_source():
    result = _translator().translate(GIS_TWO_FEEDER_BATCH)
    e1 = next(e for e in result.topology.edges if e["edge_id"] == "e1")
    assert e1["attrs"]["source"] == "gis"
    assert e1["attrs"]["external_id"] == "GIS-EDGE-E1"


def test_unknown_node_gis_id_rejected():
    bad_node = GISNodeFeature(
        gis_id="GIS-NODE-UNKNOWN",
        feature_class="busbar",
        name="unknown",
        latitude=9.0,
        longitude=7.0,
        nominal_kv=11.0,
        phases="ABC",
        attributes={},
    )
    batch = GISTopologyBatch(
        source_system="test",
        model_id="m",
        model_version="v1",
        node_features=(bad_node,) + GIS_TWO_FEEDER_BATCH.node_features[1:],
        edge_features=GIS_TWO_FEEDER_BATCH.edge_features,
    )
    result = _translator().translate(batch)
    assert any("GIS-NODE-UNKNOWN" in r.gis_id for r in result.rejections)
    assert any("identity map" in r.reason for r in result.rejections)


def test_unknown_feature_class_rejected():
    bad_node = GISNodeFeature(
        gis_id="GIS-NODE-F1",
        feature_class="unknown_gis_type",
        name="f1",
        latitude=9.0,
        longitude=7.0,
        nominal_kv=11.0,
        phases="ABC",
        attributes={},
    )
    batch = GISTopologyBatch(
        source_system="test",
        model_id="m",
        model_version="v1",
        node_features=(bad_node,) + GIS_TWO_FEEDER_BATCH.node_features[1:],
        edge_features=GIS_TWO_FEEDER_BATCH.edge_features,
    )
    result = _translator().translate(batch)
    assert any("unknown_gis_type" in r.reason for r in result.rejections)


def test_self_loop_edge_rejected():
    bad_edge = GISEdgeFeature(
        gis_id="GIS-EDGE-E1",
        feature_class="overhead_line",
        name="e1",
        from_gis_id="GIS-NODE-F1",
        to_gis_id="GIS-NODE-F1",  # same as from → self-loop
        is_switchable=False,
        normally_closed=True,
        is_closed=True,
        rating_kw=1000.0,
        phases="ABC",
        attributes={},
    )
    batch = GISTopologyBatch(
        source_system="test",
        model_id="m",
        model_version="v1",
        node_features=GIS_TWO_FEEDER_BATCH.node_features,
        edge_features=(bad_edge,) + GIS_TWO_FEEDER_BATCH.edge_features[1:],
    )
    result = _translator().translate(batch)
    assert any("self-loop" in r.reason for r in result.rejections)


def test_from_node_resolution_failure_rejected():
    bad_edge = GISEdgeFeature(
        gis_id="GIS-EDGE-E1",
        feature_class="overhead_line",
        name="e1",
        from_gis_id="GIS-NODE-MISSING",  # not in identity map
        to_gis_id="GIS-NODE-A",
        is_switchable=False,
        normally_closed=True,
        is_closed=True,
        rating_kw=1000.0,
        phases="ABC",
        attributes={},
    )
    batch = GISTopologyBatch(
        source_system="test",
        model_id="m",
        model_version="v1",
        node_features=GIS_TWO_FEEDER_BATCH.node_features,
        edge_features=(bad_edge,) + GIS_TWO_FEEDER_BATCH.edge_features[1:],
    )
    result = _translator().translate(batch)
    assert any("from_node resolution failed" in r.reason for r in result.rejections)


def test_all_features_rejected_yields_failure():
    identity = GISAssetIdentityMap({})  # empty map — nothing resolves
    translator = GISTopologyTranslator(identity)
    result = translator.translate(GIS_TWO_FEEDER_BATCH)
    assert not result.success
    assert result.topology is None
    assert len(result.rejections) == 13


def test_translation_is_deterministic():
    t1 = _translator()
    t2 = _translator()
    r1 = t1.translate(GIS_TWO_FEEDER_BATCH)
    r2 = t2.translate(GIS_TWO_FEEDER_BATCH)
    assert r1.topology.nodes == r2.topology.nodes
    assert r1.topology.edges == r2.topology.edges
