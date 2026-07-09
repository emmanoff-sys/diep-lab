"""WP-011-02 OA-078 — connector reliability tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _scada_connector_fixtures import full_pipeline  # noqa: E402

from services.scada_connector import (  # noqa: E402
    DeadLetterQueue,
    DeadLetterRecord,
    EventBuffer,
    ExponentialBackoff,
    SCADAConnectorError,
    SCADAMessage,
)
from services.scada_connector.harness.datasets import (  # noqa: E402
    CANONICAL_FAULT_EVENT,
    make_scada_messages,
)

# --- ExponentialBackoff --------------------------------------------------------


def test_backoff_doubles_per_attempt():
    bo = ExponentialBackoff(base_s=1.0, max_s=300.0)
    assert bo.delay_for(0) == 1.0
    assert bo.delay_for(1) == 2.0
    assert bo.delay_for(2) == 4.0
    assert bo.delay_for(3) == 8.0


def test_backoff_caps_at_max():
    bo = ExponentialBackoff(base_s=1.0, max_s=10.0)
    assert bo.delay_for(10) == 10.0
    assert bo.delay_for(100) == 10.0


def test_backoff_deterministic():
    bo1 = ExponentialBackoff(base_s=2.0, max_s=120.0)
    bo2 = ExponentialBackoff(base_s=2.0, max_s=120.0)
    assert bo1.delays(8) == bo2.delays(8)


def test_backoff_invalid_params_rejected():
    with pytest.raises(SCADAConnectorError):
        ExponentialBackoff(base_s=0.0)
    with pytest.raises(SCADAConnectorError):
        ExponentialBackoff(base_s=10.0, max_s=5.0)


# --- EventBuffer ---------------------------------------------------------------


def test_buffer_enqueue_and_dequeue():
    buf = EventBuffer(capacity=10)
    buf.enqueue(CANONICAL_FAULT_EVENT)
    assert buf.size == 1
    msg = buf.dequeue()
    assert msg is CANONICAL_FAULT_EVENT
    assert buf.size == 0
    assert buf.dequeue() is None


def test_buffer_overflow_drops_oldest():
    buf = EventBuffer(capacity=3)
    msgs = make_scada_messages(
        *[
            ("RTU-01:CB-E1", "status_change", i, {"status": "open", "available": False})
            for i in range(1, 6)
        ]
    )
    for msg in msgs:
        buf.enqueue(msg)
    assert buf.size == 3
    assert buf.overflow_count == 2
    remaining = buf.drain()
    assert remaining[0].sequence == 3  # oldest two dropped


def test_buffer_drain_clears():
    buf = EventBuffer(capacity=5)
    buf.enqueue(CANONICAL_FAULT_EVENT)
    drained = buf.drain()
    assert len(drained) == 1
    assert buf.size == 0


def test_buffer_invalid_capacity_rejected():
    with pytest.raises(SCADAConnectorError):
        EventBuffer(capacity=0)


# --- DeadLetterQueue -----------------------------------------------------------


def test_dead_letter_append_and_retrieve():
    dlq = DeadLetterQueue(capacity=10)
    record = DeadLetterRecord(
        message_id="m-001",
        external_asset_id="RTU-01:CB-E1",
        reason="asset not found",
        occurred_at="2026-07-09T20:00:00Z",
    )
    dlq.append(record)
    assert dlq.count == 1
    assert dlq.records[0] is record


def test_dead_letter_overflow_drops_oldest():
    dlq = DeadLetterQueue(capacity=2)
    for i in range(4):
        dlq.append(DeadLetterRecord(f"m-{i}", "ext", "reason", "t"))
    assert dlq.count == 2
    assert dlq.overflow_count == 2
    assert dlq.records[0].message_id == "m-2"


# --- ConnectorPipeline ---------------------------------------------------------


def test_pipeline_processes_valid_message():
    _, repository, pipeline = full_pipeline()
    pipeline.enqueue(CANONICAL_FAULT_EVENT)
    count = pipeline.process_buffered(occurred_at="2026-07-09T20:00:00Z")
    assert count == 1
    results = pipeline.results
    assert len(results) == 1
    assert results[0].translated is True
    assert results[0].submitted is True
    assert results[0].accepted is True
    assert results[0].dead_lettered is False
    assert repository.get_state("e1", asset_kind="edge") is not None


def test_pipeline_dead_letters_untranslatable():
    _, _, pipeline = full_pipeline()
    bad_msg = SCADAMessage(
        message_id="BAD:001",
        external_asset_id="UNKNOWN-ASSET",
        message_type="status_change",
        observed_at="2026-07-09T20:00:00Z",
        sequence=1,
        raw_payload={"status": "open", "available": False},
    )
    pipeline.enqueue(bad_msg)
    pipeline.process_buffered()
    assert pipeline.results[0].dead_lettered is True
    assert pipeline.dead_letter_queue.count == 1


def test_pipeline_does_not_crash_on_mixed_messages():
    _, _, pipeline = full_pipeline()
    bad = SCADAMessage(
        "BAD:001",
        "UNKNOWN",
        "status_change",
        "2026-07-09T20:00:00Z",
        1,
        {"status": "open", "available": False},
    )
    pipeline.enqueue(bad)
    pipeline.enqueue(CANONICAL_FAULT_EVENT)
    count = pipeline.process_buffered()
    assert count == 2
    assert pipeline.dead_letter_queue.count == 1
    assert pipeline.results[1].accepted is True
