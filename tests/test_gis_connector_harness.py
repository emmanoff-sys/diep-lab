"""WP-011-03 OA-086 — replay and test harness integration tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.gis_connector import (  # noqa: E402
    GISAssetIdentityMap,
    GISTopologyTranslator,
)
from services.gis_connector.harness import (  # noqa: E402
    GIS_CANONICAL_IDENTITY_MAP,
    GIS_TWO_FEEDER_BATCH,
)
from services.scada_connector.harness import GisStub, SessionRecorder, SessionReplayer  # noqa: E402
from services.scada_connector.harness.contracts import validate_mapped_topology  # noqa: E402
from services.scada_connector.harness.datasets import TWO_FEEDER_TOPOLOGY  # noqa: E402


def _translate():
    identity = GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP)
    return GISTopologyTranslator(identity).translate(GIS_TWO_FEEDER_BATCH)


def test_gis_two_feeder_batch_has_correct_counts():
    assert len(GIS_TWO_FEEDER_BATCH.node_features) == 7
    assert len(GIS_TWO_FEEDER_BATCH.edge_features) == 6


def test_gis_canonical_identity_map_has_all_two_feeder_ids():
    assert len(GIS_CANONICAL_IDENTITY_MAP) == 13  # 7 nodes + 6 edges


def test_gis_stub_returns_batch():
    stub = GisStub(GIS_TWO_FEEDER_BATCH)
    model = stub.fetch_model()
    assert model is GIS_TWO_FEEDER_BATCH


def test_translated_batch_passes_contract_validation():
    result = _translate()
    assert result.success
    validate_mapped_topology(result.topology)


def test_translated_node_ids_match_two_feeder_topology():
    result = _translate()
    gis_node_ids = {n["node_id"] for n in result.topology.nodes}
    canonical_node_ids = {n["node_id"] for n in TWO_FEEDER_TOPOLOGY.nodes}
    assert gis_node_ids == canonical_node_ids


def test_translated_edge_ids_match_two_feeder_topology():
    result = _translate()
    gis_edge_ids = {e["edge_id"] for e in result.topology.edges}
    canonical_edge_ids = {e["edge_id"] for e in TWO_FEEDER_TOPOLOGY.edges}
    assert gis_edge_ids == canonical_edge_ids


def test_session_recorder_captures_raw_batch_dict():
    recorder = SessionRecorder()
    raw = {"source_system": "gis-test", "model_id": "m1", "model_version": "v1"}
    recorder.record(raw)
    assert recorder.count == 1
    assert recorder.messages()[0] == raw


def test_session_recorder_save_and_replayer_load(tmp_path):
    recorder = SessionRecorder()
    raw = {"source_system": "gis-test", "model_id": "m1", "model_version": "v1"}
    recorder.record(raw)
    path = tmp_path / "gis_session.jsonl"
    recorder.save(path)
    replayer = SessionReplayer(path)
    assert replayer.count == 1
    assert replayer.messages[0] == raw


def test_session_replayer_from_messages():
    raw1 = {"model_id": "m1"}
    raw2 = {"model_id": "m2"}
    replayer = SessionReplayer.from_messages((raw1, raw2))
    assert replayer.count == 2
    assert replayer.messages == (raw1, raw2)


def test_gis_replay_produces_identical_translation_result():
    """Two replays of the same GIS batch produce identical topology."""
    identity = GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP)
    translator = GISTopologyTranslator(identity)

    result_1 = translator.translate(GIS_TWO_FEEDER_BATCH)
    result_2 = translator.translate(GIS_TWO_FEEDER_BATCH)

    assert result_1.topology.nodes == result_2.topology.nodes
    assert result_1.topology.edges == result_2.topology.edges
    assert result_1.translated_nodes == result_2.translated_nodes
    assert result_1.translated_edges == result_2.translated_edges


def test_all_gis_node_gis_ids_in_identity_map():
    mapped = set(GIS_CANONICAL_IDENTITY_MAP.keys())
    batch_node_ids = {f.gis_id for f in GIS_TWO_FEEDER_BATCH.node_features}
    batch_edge_ids = {f.gis_id for f in GIS_TWO_FEEDER_BATCH.edge_features}
    assert batch_node_ids.issubset(mapped)
    assert batch_edge_ids.issubset(mapped)


def test_two_feeder_batch_source_system_distinct_from_scada():
    assert GIS_TWO_FEEDER_BATCH.source_system != TWO_FEEDER_TOPOLOGY.source_system
    assert "gis" in GIS_TWO_FEEDER_BATCH.source_system
