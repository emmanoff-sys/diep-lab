"""OA-092 — secure AMI event ingestion.

Adapts the WP-011-02 IngestionClient for AMI protocol use, adding
meter-ID correlation to submission records and structured per-meter
diagnostics. No new ingestion pipeline or security infrastructure is
introduced — all trust-boundary enforcement, replay protection, and
event-ID deduplication are provided by the underlying IngestionClient.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.adms_operational_state import OperationalEvent
from services.scada_connector.ingestion import IngestionClient


@dataclass(frozen=True)
class AMIIngestionRecord:
    """Outcome of submitting one AMI-derived canonical event."""

    meter_id: str
    event_id: str
    accepted: bool
    duplicate: bool
    reason: str | None


class AMIIngestionAdapter:
    """Submits AMI-derived canonical events via the WP-011-02 IngestionClient.

    Adds meter-ID correlation to each submission record so that
    downstream diagnostics can trace accepted or rejected events back
    to the originating AMI meter. All replay protection and
    deduplication are handled by the underlying IngestionClient.
    """

    def __init__(self, client: IngestionClient) -> None:
        self._client = client

    @property
    def tls_enabled(self) -> bool:
        return self._client.tls_enabled

    def submit(self, meter_id: str, event: OperationalEvent) -> AMIIngestionRecord:
        """Submit one canonical event and return a meter-correlated record."""
        result = self._client.submit(event)
        return AMIIngestionRecord(
            meter_id=meter_id,
            event_id=result.event_id,
            accepted=result.accepted,
            duplicate=result.duplicate,
            reason=result.reason,
        )

    def submit_many(
        self,
        meter_ids: tuple[str, ...],
        events: tuple[OperationalEvent, ...],
    ) -> tuple[AMIIngestionRecord, ...]:
        """Submit multiple events; meter_ids and events must be the same length."""
        if len(meter_ids) != len(events):
            raise ValueError(f"meter_ids ({len(meter_ids)}) and events ({len(events)}) must match")
        return tuple(self.submit(mid, evt) for mid, evt in zip(meter_ids, events, strict=True))

    def reset_session(self) -> None:
        """Clear the seen-event-ID set at the start of a new session."""
        self._client.reset_session()
