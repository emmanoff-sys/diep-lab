"""OA-096 — GIS connector reliability layer.

Topology batch buffering, dead-letter recording, and a pipeline runner for
the GIS topology adapter. Mirrors the scada_connector reliability model so
that operational behaviour is consistent across all three connectors.

GIS processes complete topology snapshots (batches) rather than individual
events. A batch is dead-lettered when translation produces no usable output
(zero nodes or zero edges). Individual feature rejections are not dead-
lettered — they are expected and captured in GISTranslationResult.rejections
for operator review via the reconciliation workflow.

Generic primitives (DeadLetterQueue, DeadLetterRecord, ExponentialBackoff)
are re-exported from services.scada_connector.reliability.

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

from .framework import GISConnectorError
from .translation import GISTopologyBatch, GISTranslationResult

__all__ = [
    "DeadLetterQueue",
    "DeadLetterRecord",
    "ExponentialBackoff",
    "GISConnectorPipeline",
    "GISPipelineResult",
    "GISTopologyBuffer",
]


class GISTopologyBuffer:
    """Bounded FIFO buffer for GISTopologyBatch objects awaiting pipeline processing.

    On overflow the oldest batch is dropped and the overflow counter
    incremented. Never blocks; always deterministic.
    """

    def __init__(self, capacity: int = 100) -> None:
        if capacity < 1:
            raise GISConnectorError("buffer capacity must be ≥ 1")
        self._capacity = capacity
        self._queue: deque[GISTopologyBatch] = deque()
        self._overflow_count = 0

    def enqueue(self, batch: GISTopologyBatch) -> None:
        if len(self._queue) >= self._capacity:
            self._queue.popleft()
            self._overflow_count += 1
        self._queue.append(batch)

    def dequeue(self) -> GISTopologyBatch | None:
        return self._queue.popleft() if self._queue else None

    def drain(self) -> tuple[GISTopologyBatch, ...]:
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
class GISPipelineResult:
    """Outcome of processing one GISTopologyBatch through the translation pipeline."""

    model_id: str
    model_version: str
    translated: bool
    translated_nodes: int
    translated_edges: int
    rejection_count: int
    dead_lettered: bool
    detail: str


class GISConnectorPipeline:
    """Ties GIS translation, buffering, and dead-letter together.

    The pipeline processes topology batches: fetch → buffer → translate →
    record outcome. A batch is dead-lettered when translation fails
    completely (success=False, i.e. zero nodes or zero edges translated).
    Partially successful batches (some feature rejections but at least one
    node and one edge translated) are not dead-lettered — the rejections
    are accessible in the translation result for operator review.

    Reconciliation is a separate advisory step: callers receive the
    MappedTopology via pipeline.results and independently invoke
    TopologyReconciler as needed.
    """

    def __init__(
        self,
        translator: object,
        *,
        buffer_capacity: int = 100,
        dead_letter_capacity: int = 1000,
    ) -> None:
        self._translator = translator
        self._buffer = GISTopologyBuffer(capacity=buffer_capacity)
        self._dead_letter = DeadLetterQueue(capacity=dead_letter_capacity)
        self._results: list[GISPipelineResult] = []

    def enqueue(self, batch: GISTopologyBatch) -> None:
        self._buffer.enqueue(batch)

    def process_buffered(self, occurred_at: str = "1970-01-01T00:00:00Z") -> int:
        """Drain the buffer and translate each batch; returns count processed."""
        batches = self._buffer.drain()
        for batch in batches:
            result = self._process_one(batch, occurred_at)
            self._results.append(result)
        return len(batches)

    def _process_one(self, batch: GISTopologyBatch, occurred_at: str) -> GISPipelineResult:
        translation: GISTranslationResult = self._translator.translate(batch)
        if not translation.success:
            reason = (
                f"translation failed: {translation.translated_nodes} nodes, "
                f"{translation.translated_edges} edges translated from "
                f"{translation.total_features} features"
            )
            self._dead_letter.append(
                DeadLetterRecord(
                    message_id=batch.model_id,
                    external_asset_id=batch.source_system,
                    reason=reason,
                    occurred_at=occurred_at,
                )
            )
            return GISPipelineResult(
                model_id=batch.model_id,
                model_version=batch.model_version,
                translated=False,
                translated_nodes=translation.translated_nodes,
                translated_edges=translation.translated_edges,
                rejection_count=len(translation.rejections),
                dead_lettered=True,
                detail=reason,
            )

        return GISPipelineResult(
            model_id=batch.model_id,
            model_version=batch.model_version,
            translated=True,
            translated_nodes=translation.translated_nodes,
            translated_edges=translation.translated_edges,
            rejection_count=len(translation.rejections),
            dead_lettered=False,
            detail=(
                f"translated {translation.translated_nodes} nodes, "
                f"{translation.translated_edges} edges"
                + (
                    f" ({len(translation.rejections)} feature(s) rejected)"
                    if translation.rejections
                    else ""
                )
            ),
        )

    @property
    def results(self) -> tuple[GISPipelineResult, ...]:
        return tuple(self._results)

    @property
    def dead_letter_queue(self) -> DeadLetterQueue:
        return self._dead_letter

    @property
    def buffer(self) -> GISTopologyBuffer:
        return self._buffer
