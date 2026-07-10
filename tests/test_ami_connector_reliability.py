"""OA-096 — AMI connector reliability tests (WP-026).

Covers AMIEventBuffer, AMIConnectorPipeline, and the re-exported generic
reliability primitives (ExponentialBackoff, DeadLetterQueue, DeadLetterRecord).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from services.ami_connector import (  # noqa: E402
    AMIConnectorPipeline,
    AMIEventBuffer,
    AMIEventTranslator,
    AMIIngestionAdapter,
    AMIMessage,
    AMIMeterIdentityMap,
    DeadLetterQueue,
    DeadLetterRecord,
    ExponentialBackoff,
)
from services.ami_connector.framework import AMIConnectorError  # noqa: E402
from services.ami_connector.harness import (  # noqa: E402
    AMI_CANONICAL_BATCH,
    AMI_CANONICAL_METER_MAP,
    AMI_LAST_GASP_EVENT,
)

sys.path.insert(0, os.path.dirname(__file__))
from _scada_connector_fixtures import connector_stack  # noqa: E402

# --- Helpers -------------------------------------------------------------------


def _make_translator():
    known = frozenset(["c", "e"])
    identity_map = AMIMeterIdentityMap(AMI_CANONICAL_METER_MAP, known_asset_ids=known)
    return AMIEventTranslator(identity_map, actor="test-ami")


# --- AMIEventBuffer ------------------------------------------------------------


def test_ami_buffer_enqueue_and_dequeue():
    buf = AMIEventBuffer(capacity=10)
    buf.enqueue(AMI_LAST_GASP_EVENT)
    assert buf.size == 1
    msg = buf.dequeue()
    assert msg is AMI_LAST_GASP_EVENT
    assert buf.size == 0
    assert buf.dequeue() is None


def test_ami_buffer_overflow_drops_oldest():
    buf = AMIEventBuffer(capacity=2)
    msgs = [
        AMIMessage(
            f"AMI:METER-C-001:LASTGASP:{i:03}",
            "AMI:METER-C-001",
            "last_gasp",
            "2026-07-10T06:00:00Z",
            i,
            {"available": False},
        )
        for i in range(1, 5)
    ]
    for m in msgs:
        buf.enqueue(m)
    assert buf.size == 2
    assert buf.overflow_count == 2
    drained = buf.drain()
    assert drained[0].sequence == 3  # oldest two dropped


def test_ami_buffer_drain_clears():
    buf = AMIEventBuffer(capacity=5)
    buf.enqueue(AMI_LAST_GASP_EVENT)
    drained = buf.drain()
    assert len(drained) == 1
    assert buf.size == 0


def test_ami_buffer_invalid_capacity_rejected():
    with pytest.raises(AMIConnectorError):
        AMIEventBuffer(capacity=0)


# --- Re-exported generic primitives --------------------------------------------


def test_exponential_backoff_reused_from_scada():
    bo = ExponentialBackoff(base_s=1.0, max_s=300.0)
    assert bo.delay_for(0) == 1.0
    assert bo.delay_for(3) == 8.0
    assert bo.delay_for(100) == 300.0


def test_dead_letter_queue_reused_from_scada():
    dlq = DeadLetterQueue(capacity=5)
    record = DeadLetterRecord("m-001", "AMI:METER-C-001", "test reason", "2026-07-10T00:00:00Z")
    dlq.append(record)
    assert dlq.count == 1
    assert dlq.records[0].message_id == "m-001"


def test_dead_letter_queue_overflow_drops_oldest():
    dlq = DeadLetterQueue(capacity=2)
    for i in range(4):
        dlq.append(DeadLetterRecord(f"m-{i}", "meter", "reason", "t"))
    assert dlq.count == 2
    assert dlq.overflow_count == 2
    assert dlq.records[0].message_id == "m-2"


# --- AMIConnectorPipeline ------------------------------------------------------


def _make_full_pipeline():
    """Returns (pipeline, raw_ingestion_client) for pipeline integration tests."""
    _, repository, translator_scada, ingestion_client, _ = connector_stack()
    known = frozenset(["c", "e"])
    identity_map = AMIMeterIdentityMap(AMI_CANONICAL_METER_MAP, known_asset_ids=known)
    translator = AMIEventTranslator(identity_map, actor="test-ami")
    adapter = AMIIngestionAdapter(ingestion_client)
    pipeline = AMIConnectorPipeline(translator, adapter)
    return pipeline


def test_pipeline_processes_valid_last_gasp():
    pipeline = _make_full_pipeline()
    pipeline.enqueue(AMI_LAST_GASP_EVENT)
    count = pipeline.process_buffered(occurred_at="2026-07-10T06:00:00Z")
    assert count == 1
    results = pipeline.results
    assert len(results) == 1
    r = results[0]
    assert r.translated is True
    assert r.submitted is True
    assert r.accepted is True
    assert r.dead_lettered is False
    assert r.meter_id == AMI_LAST_GASP_EVENT.meter_id


def test_pipeline_dead_letters_unknown_meter():
    pipeline = _make_full_pipeline()
    bad_msg = AMIMessage(
        message_id="UNKNOWN:001",
        meter_id="AMI:METER-UNKNOWN:001",
        message_type="last_gasp",
        observed_at="2026-07-10T06:00:00Z",
        sequence=1,
        raw_payload={"available": False},
    )
    pipeline.enqueue(bad_msg)
    pipeline.process_buffered()
    assert pipeline.results[0].dead_lettered is True
    assert pipeline.results[0].translated is False
    assert pipeline.dead_letter_queue.count == 1


def test_pipeline_dead_letters_unknown_message_type():
    pipeline = _make_full_pipeline()
    bad_msg = AMIMessage(
        message_id="AMI:METER-C-001:UNKNOWN:001",
        meter_id="AMI:METER-C-001",
        message_type="unknown_type",
        observed_at="2026-07-10T06:00:00Z",
        sequence=1,
        raw_payload={"available": False},
    )
    pipeline.enqueue(bad_msg)
    pipeline.process_buffered()
    assert pipeline.results[0].dead_lettered is True
    assert pipeline.dead_letter_queue.count == 1


def test_pipeline_duplicate_not_dead_lettered():
    pipeline = _make_full_pipeline()
    # Submit same event twice — second is a duplicate
    pipeline.enqueue(AMI_LAST_GASP_EVENT)
    pipeline.enqueue(AMI_LAST_GASP_EVENT)
    pipeline.process_buffered()
    results = pipeline.results
    assert results[0].accepted is True
    assert results[0].dead_lettered is False
    assert results[1].dead_lettered is False  # duplicate skipped, not dead-lettered
    assert results[1].detail == "duplicate (skipped)"
    assert pipeline.dead_letter_queue.count == 0


def test_pipeline_processes_canonical_batch():
    pipeline = _make_full_pipeline()
    for msg in AMI_CANONICAL_BATCH:
        pipeline.enqueue(msg)
    count = pipeline.process_buffered(occurred_at="2026-07-10T07:00:00Z")
    assert count == 4
    results = pipeline.results
    assert all(r.accepted for r in results)
    assert pipeline.dead_letter_queue.count == 0


def test_pipeline_buffer_and_dead_letter_accessible():
    pipeline = _make_full_pipeline()
    assert pipeline.buffer.size == 0
    assert pipeline.dead_letter_queue.count == 0
    pipeline.enqueue(AMI_LAST_GASP_EVENT)
    assert pipeline.buffer.size == 1
