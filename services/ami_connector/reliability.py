"""OA-096 — AMI connector reliability layer.

Event buffering, dead-letter recording, and a pipeline runner for the AMI
metering connector. Mirrors the scada_connector reliability model so that
operational behaviour is consistent across all three connectors.

Generic primitives (DeadLetterQueue, DeadLetterRecord, ExponentialBackoff)
are re-exported from services.scada_connector.reliability — they carry no
SCADA-specific type constraints and are shared across the connector suite.

Everything is deterministic: no wall clock, no sleep.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from services.scada_connector.reliability import (
    DeadLetterQueue,
    DeadLetterRecord,
    ExponentialBackoff,
)

from .framework import AMIConnectorError
from .translation import AMIMessage, AMITranslationResult

__all__ = [
    "AMIConnectorPipeline",
    "AMIEventBuffer",
    "AMIPipelineResult",
    "DeadLetterQueue",
    "DeadLetterRecord",
    "ExponentialBackoff",
]


class AMIEventBuffer:
    """Bounded FIFO buffer for AMIMessage objects awaiting pipeline processing.

    On overflow the oldest message is dropped and the overflow counter
    incremented. Never blocks; always deterministic.
    """

    def __init__(self, capacity: int = 1000) -> None:
        if capacity < 1:
            raise AMIConnectorError("buffer capacity must be ≥ 1")
        self._capacity = capacity
        self._queue: deque[AMIMessage] = deque()
        self._overflow_count = 0

    def enqueue(self, message: AMIMessage) -> None:
        if len(self._queue) >= self._capacity:
            self._queue.popleft()
            self._overflow_count += 1
        self._queue.append(message)

    def dequeue(self) -> AMIMessage | None:
        return self._queue.popleft() if self._queue else None

    def drain(self) -> tuple[AMIMessage, ...]:
        items = tuple(self._queue)
        self._queue.clear()
        return items

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def overflow_count(self) -> int:
        return self._overflow_count


@dataclass(frozen=True)
class AMIPipelineResult:
    """Outcome of processing one AMIMessage through the full pipeline."""

    message_id: str
    meter_id: str
    translated: bool
    submitted: bool
    accepted: bool
    dead_lettered: bool
    detail: str


class AMIConnectorPipeline:
    """Ties AMI translation, ingestion, buffering, and dead-letter together.

    The pipeline is the single unit of work for an AMI connector session:
    receive → buffer → translate → submit → record outcome. Dead-letter
    entries are written for messages that fail translation or are rejected
    by the ingestion adapter (duplicates are not dead-lettered — they are
    expected and benign replay artefacts).
    """

    def __init__(
        self,
        translator: object,
        ingestion_adapter: object,
        *,
        buffer_capacity: int = 1000,
        dead_letter_capacity: int = 1000,
    ) -> None:
        self._translator = translator
        self._ingestion = ingestion_adapter
        self._buffer = AMIEventBuffer(capacity=buffer_capacity)
        self._dead_letter = DeadLetterQueue(capacity=dead_letter_capacity)
        self._results: list[AMIPipelineResult] = []

    def enqueue(self, message: AMIMessage) -> None:
        self._buffer.enqueue(message)

    def process_buffered(self, occurred_at: str = "1970-01-01T00:00:00Z") -> int:
        """Drain the buffer and process each message; returns count processed."""
        messages = self._buffer.drain()
        for message in messages:
            result = self._process_one(message, occurred_at)
            self._results.append(result)
        return len(messages)

    def _process_one(self, message: AMIMessage, occurred_at: str) -> AMIPipelineResult:
        translation: AMITranslationResult = self._translator.translate(message)
        if not translation.success:
            reason = translation.rejection.reason if translation.rejection else "translation failed"
            self._dead_letter.append(
                DeadLetterRecord(
                    message_id=message.message_id,
                    external_asset_id=message.meter_id,
                    reason=reason,
                    occurred_at=occurred_at,
                )
            )
            return AMIPipelineResult(
                message_id=message.message_id,
                meter_id=message.meter_id,
                translated=False,
                submitted=False,
                accepted=False,
                dead_lettered=True,
                detail=reason,
            )

        assert translation.event is not None
        record = self._ingestion.submit(message.meter_id, translation.event)

        if not record.accepted and not record.duplicate:
            reason = record.reason or "ingestion rejected"
            self._dead_letter.append(
                DeadLetterRecord(
                    message_id=message.message_id,
                    external_asset_id=message.meter_id,
                    reason=reason,
                    occurred_at=occurred_at,
                )
            )
            return AMIPipelineResult(
                message_id=message.message_id,
                meter_id=message.meter_id,
                translated=True,
                submitted=True,
                accepted=False,
                dead_lettered=True,
                detail=reason,
            )

        return AMIPipelineResult(
            message_id=message.message_id,
            meter_id=message.meter_id,
            translated=True,
            submitted=True,
            accepted=record.accepted,
            dead_lettered=False,
            detail="accepted" if record.accepted else "duplicate (skipped)",
        )

    @property
    def results(self) -> tuple[AMIPipelineResult, ...]:
        return tuple(self._results)

    @property
    def dead_letter_queue(self) -> DeadLetterQueue:
        return self._dead_letter

    @property
    def buffer(self) -> AMIEventBuffer:
        return self._buffer
