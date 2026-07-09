"""OA-078 — connector reliability.

Deterministic backoff calculation, bounded event buffer, dead-letter
recording, and a pipeline runner that ties them together.

Everything is deterministic: the backoff takes attempt number as input
(no sleep, no wall clock); the buffer drops oldest on overflow; the
dead-letter queue is bounded and append-only.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .framework import SCADAConnectorError
from .translation import SCADAMessage


@dataclass(frozen=True)
class DeadLetterRecord:
    message_id: str
    external_asset_id: str
    reason: str
    occurred_at: str


class DeadLetterQueue:
    """Bounded append-only dead-letter queue.

    When at capacity, the oldest entry is discarded to make room —
    the queue never blocks and never raises on overflow. The overflow
    counter allows health monitoring without inspecting records.
    """

    def __init__(self, capacity: int = 1000) -> None:
        if capacity < 1:
            raise SCADAConnectorError("dead-letter capacity must be ≥ 1")
        self._capacity = capacity
        self._records: deque[DeadLetterRecord] = deque()
        self._overflow_count = 0

    def append(self, record: DeadLetterRecord) -> None:
        if len(self._records) >= self._capacity:
            self._records.popleft()
            self._overflow_count += 1
        self._records.append(record)

    @property
    def records(self) -> tuple[DeadLetterRecord, ...]:
        return tuple(self._records)

    @property
    def count(self) -> int:
        return len(self._records)

    @property
    def overflow_count(self) -> int:
        return self._overflow_count


class EventBuffer:
    """Bounded FIFO buffer for raw SCADA messages awaiting translation.

    On overflow the oldest message is dropped and the overflow counter
    incremented. Never blocks; always deterministic.
    """

    def __init__(self, capacity: int = 1000) -> None:
        if capacity < 1:
            raise SCADAConnectorError("buffer capacity must be ≥ 1")
        self._capacity = capacity
        self._queue: deque[SCADAMessage] = deque()
        self._overflow_count = 0

    def enqueue(self, message: SCADAMessage) -> None:
        if len(self._queue) >= self._capacity:
            self._queue.popleft()
            self._overflow_count += 1
        self._queue.append(message)

    def dequeue(self) -> SCADAMessage | None:
        return self._queue.popleft() if self._queue else None

    def drain(self) -> tuple[SCADAMessage, ...]:
        items = tuple(self._queue)
        self._queue.clear()
        return items

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def overflow_count(self) -> int:
        return self._overflow_count


class ExponentialBackoff:
    """Deterministic backoff schedule.

    `delay_for(attempt)` returns the delay in seconds for the given
    attempt number (0-indexed). No randomness, no wall clock — the
    caller decides when to actually wait.
    """

    def __init__(self, base_s: float = 1.0, max_s: float = 300.0) -> None:
        if base_s <= 0:
            raise SCADAConnectorError("backoff base must be > 0")
        if max_s < base_s:
            raise SCADAConnectorError("backoff max must be ≥ base")
        self._base = base_s
        self._max = max_s

    def delay_for(self, attempt: int) -> float:
        """Return delay in seconds for zero-indexed attempt number."""
        return min(self._base * (2**attempt), self._max)

    def delays(self, max_attempts: int) -> tuple[float, ...]:
        return tuple(self.delay_for(i) for i in range(max_attempts))


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of processing one message through the full pipeline."""

    message_id: str
    translated: bool
    submitted: bool
    accepted: bool
    dead_lettered: bool
    detail: str


class ConnectorPipeline:
    """Ties translation, ingestion, reliability, and dead-letter together.

    The pipeline is the single unit of work for a connector session:
    receive → buffer → translate → submit → record outcome.
    """

    def __init__(
        self,
        translator: Any,
        ingestion_client: Any,
        *,
        buffer_capacity: int = 1000,
        dead_letter_capacity: int = 1000,
    ) -> None:
        self._translator = translator
        self._ingestion = ingestion_client
        self._buffer = EventBuffer(capacity=buffer_capacity)
        self._dead_letter = DeadLetterQueue(capacity=dead_letter_capacity)
        self._results: list[PipelineResult] = []

    def enqueue(self, message: SCADAMessage) -> None:
        self._buffer.enqueue(message)

    def process_buffered(self, occurred_at: str = "1970-01-01T00:00:00Z") -> int:
        """Drain the buffer and process each message; returns count processed."""
        messages = self._buffer.drain()
        for message in messages:
            result = self._process_one(message, occurred_at)
            self._results.append(result)
        return len(messages)

    def _process_one(self, message: SCADAMessage, occurred_at: str) -> PipelineResult:
        translation = self._translator.translate(message)
        if not translation.success:
            record = DeadLetterRecord(
                message_id=message.message_id,
                external_asset_id=message.external_asset_id,
                reason=translation.rejection_reason or "translation failed",
                occurred_at=occurred_at,
            )
            self._dead_letter.append(record)
            return PipelineResult(
                message_id=message.message_id,
                translated=False,
                submitted=False,
                accepted=False,
                dead_lettered=True,
                detail=record.reason,
            )
        ingestion_result = self._ingestion.submit(translation.event)
        if not ingestion_result.accepted:
            if not ingestion_result.duplicate:
                record = DeadLetterRecord(
                    message_id=message.message_id,
                    external_asset_id=message.external_asset_id,
                    reason=ingestion_result.reason or "ingestion rejected",
                    occurred_at=occurred_at,
                )
                self._dead_letter.append(record)
                return PipelineResult(
                    message_id=message.message_id,
                    translated=True,
                    submitted=True,
                    accepted=False,
                    dead_lettered=True,
                    detail=record.reason,
                )
        return PipelineResult(
            message_id=message.message_id,
            translated=True,
            submitted=True,
            accepted=ingestion_result.accepted,
            dead_lettered=False,
            detail="accepted" if ingestion_result.accepted else "duplicate (skipped)",
        )

    @property
    def results(self) -> tuple[PipelineResult, ...]:
        return tuple(self._results)

    @property
    def dead_letter_queue(self) -> DeadLetterQueue:
        return self._dead_letter

    @property
    def buffer(self) -> EventBuffer:
        return self._buffer
