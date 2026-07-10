"""OA-096 — GIS connector reliability tests (WP-026).

Covers GISTopologyBuffer, GISConnectorPipeline, and the re-exported generic
reliability primitives (ExponentialBackoff, DeadLetterQueue, DeadLetterRecord).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from services.gis_connector import (  # noqa: E402
    DeadLetterQueue,
    DeadLetterRecord,
    ExponentialBackoff,
    GISAssetIdentityMap,
    GISConnectorPipeline,
    GISTopologyBatch,
    GISTopologyBuffer,
    GISTopologyTranslator,
)
from services.gis_connector.framework import GISConnectorError  # noqa: E402
from services.gis_connector.harness import (  # noqa: E402
    GIS_CANONICAL_IDENTITY_MAP,
    GIS_TWO_FEEDER_BATCH,
)
from services.gis_connector.translation import GISNodeFeature  # noqa: E402

# --- Helpers -------------------------------------------------------------------


def _translator() -> GISTopologyTranslator:
    return GISTopologyTranslator(GISAssetIdentityMap(GIS_CANONICAL_IDENTITY_MAP))


def _empty_batch() -> GISTopologyBatch:
    return GISTopologyBatch(
        source_system="test-gis",
        model_id="empty-model",
        model_version="0.0.0",
        node_features=(),
        edge_features=(),
    )


def _unresolvable_batch() -> GISTopologyBatch:
    """A batch containing only features with unknown GIS IDs (no identity map entries)."""
    return GISTopologyBatch(
        source_system="test-gis",
        model_id="bad-model",
        model_version="0.0.0",
        node_features=(
            GISNodeFeature(
                gis_id="GIS-NODE-UNKNOWN",
                feature_class="feeder",
                name="Unknown",
                latitude=0.0,
                longitude=0.0,
                nominal_kv=0.0,
                phases="ABC",
                attributes={},
            ),
        ),
        edge_features=(),
    )


# --- GISTopologyBuffer ---------------------------------------------------------


def test_gis_buffer_enqueue_and_dequeue():
    buf = GISTopologyBuffer(capacity=5)
    buf.enqueue(GIS_TWO_FEEDER_BATCH)
    assert buf.size == 1
    batch = buf.dequeue()
    assert batch is GIS_TWO_FEEDER_BATCH
    assert buf.size == 0
    assert buf.dequeue() is None


def test_gis_buffer_overflow_drops_oldest():
    buf = GISTopologyBuffer(capacity=2)
    batches = [GISTopologyBatch("test-gis", f"model-{i}", f"v{i}", (), ()) for i in range(4)]
    for b in batches:
        buf.enqueue(b)
    assert buf.size == 2
    assert buf.overflow_count == 2
    drained = buf.drain()
    assert drained[0].model_id == "model-2"  # oldest two dropped


def test_gis_buffer_drain_clears():
    buf = GISTopologyBuffer(capacity=5)
    buf.enqueue(GIS_TWO_FEEDER_BATCH)
    drained = buf.drain()
    assert len(drained) == 1
    assert buf.size == 0


def test_gis_buffer_invalid_capacity_rejected():
    with pytest.raises(GISConnectorError):
        GISTopologyBuffer(capacity=0)


# --- Re-exported generic primitives --------------------------------------------


def test_exponential_backoff_reused_from_scada():
    bo = ExponentialBackoff(base_s=2.0, max_s=60.0)
    assert bo.delay_for(0) == 2.0
    assert bo.delay_for(1) == 4.0
    assert bo.delay_for(10) == 60.0


def test_dead_letter_queue_reused_from_scada():
    dlq = DeadLetterQueue(capacity=5)
    record = DeadLetterRecord("model-001", "test-gis", "translation failed", "2026-07-10T00:00:00Z")
    dlq.append(record)
    assert dlq.count == 1
    assert dlq.records[0].message_id == "model-001"


# --- GISConnectorPipeline ------------------------------------------------------


def test_pipeline_processes_valid_batch():
    pipeline = GISConnectorPipeline(_translator())
    pipeline.enqueue(GIS_TWO_FEEDER_BATCH)
    count = pipeline.process_buffered(occurred_at="2026-07-10T06:00:00Z")
    assert count == 1
    results = pipeline.results
    assert len(results) == 1
    r = results[0]
    assert r.translated is True
    assert r.dead_lettered is False
    assert r.translated_nodes == 7
    assert r.translated_edges == 6
    assert r.model_id == GIS_TWO_FEEDER_BATCH.model_id


def test_pipeline_dead_letters_empty_batch():
    pipeline = GISConnectorPipeline(_translator())
    pipeline.enqueue(_empty_batch())
    pipeline.process_buffered()
    assert pipeline.results[0].dead_lettered is True
    assert pipeline.results[0].translated is False
    assert pipeline.dead_letter_queue.count == 1
    assert pipeline.dead_letter_queue.records[0].message_id == "empty-model"


def test_pipeline_dead_letters_unresolvable_batch():
    """A batch with only unknown GIS IDs produces zero output → dead-lettered."""
    pipeline = GISConnectorPipeline(_translator())
    pipeline.enqueue(_unresolvable_batch())
    pipeline.process_buffered()
    assert pipeline.results[0].dead_lettered is True
    assert pipeline.dead_letter_queue.count == 1


def test_pipeline_partial_rejection_not_dead_lettered():
    """A batch with some unknown features but at least one node+edge → NOT dead-lettered."""
    from services.gis_connector.translation import GISNodeFeature

    partial_batch = GISTopologyBatch(
        source_system="test-gis",
        model_id="partial-model",
        model_version="v1",
        node_features=GIS_TWO_FEEDER_BATCH.node_features
        + (
            GISNodeFeature(
                gis_id="GIS-NODE-UNKNOWN-EXTRA",
                feature_class="feeder",
                name="Unknown",
                latitude=0.0,
                longitude=0.0,
                nominal_kv=0.0,
                phases="ABC",
                attributes={},
            ),
        ),
        edge_features=GIS_TWO_FEEDER_BATCH.edge_features,
    )
    pipeline = GISConnectorPipeline(_translator())
    pipeline.enqueue(partial_batch)
    pipeline.process_buffered()
    r = pipeline.results[0]
    assert r.translated is True
    assert r.dead_lettered is False
    assert r.rejection_count == 1  # one unknown node rejected but batch succeeded


def test_pipeline_processes_multiple_batches():
    pipeline = GISConnectorPipeline(_translator())
    pipeline.enqueue(GIS_TWO_FEEDER_BATCH)
    pipeline.enqueue(_empty_batch())
    pipeline.enqueue(GIS_TWO_FEEDER_BATCH)
    count = pipeline.process_buffered()
    assert count == 3
    results = pipeline.results
    assert results[0].translated is True
    assert results[1].dead_lettered is True
    assert results[2].translated is True
    assert pipeline.dead_letter_queue.count == 1


def test_pipeline_buffer_and_dead_letter_accessible():
    pipeline = GISConnectorPipeline(_translator())
    assert pipeline.buffer.size == 0
    assert pipeline.dead_letter_queue.count == 0
    pipeline.enqueue(GIS_TWO_FEEDER_BATCH)
    assert pipeline.buffer.size == 1
