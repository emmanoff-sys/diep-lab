"""OA-077 — secure event ingestion.

Wraps the WP-008 OperationalEventProcessor with trust-boundary
enforcement (mTLS configuration), replay protection (event-id
deduplication within a session), and structured submission results.

No secrets are stored here. Certificate paths are injected by the
caller from the environment (per OA-072 §5).
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass

from services.adms_operational_state import OperationalEvent, OperationalEventProcessor

from .framework import SCADAConnectorError


@dataclass(frozen=True)
class TLSContext:
    """mTLS configuration for a connector instance.

    Paths are absolute filesystem paths; they are validated at
    construction time to be non-empty strings. The actual certificates
    are loaded only when `build_ssl_context()` is called — not stored
    here so this dataclass carries no secret material.
    """

    client_cert_path: str
    client_key_path: str
    ca_cert_path: str

    def __post_init__(self) -> None:
        if not self.client_cert_path:
            raise SCADAConnectorError("client_cert_path is required for mTLS")
        if not self.client_key_path:
            raise SCADAConnectorError("client_key_path is required for mTLS")
        if not self.ca_cert_path:
            raise SCADAConnectorError("ca_cert_path is required for mTLS")

    def build_ssl_context(self) -> ssl.SSLContext:
        """Build a client-side mTLS ssl.SSLContext from the configured paths."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_cert_chain(self.client_cert_path, self.client_key_path)
        ctx.load_verify_locations(self.ca_cert_path)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        return ctx


@dataclass(frozen=True)
class IngestionResult:
    event_id: str
    accepted: bool
    duplicate: bool
    reason: str | None


class IngestionClient:
    """Submits translated canonical events to the WP-008 ingestion pipeline.

    Maintains a session-scoped seen-event-id set for replay protection:
    an event_id that has already been submitted in this session is
    rejected as a duplicate without re-submitting to the engine (the
    engine's own sequence check also guards against stale sequences,
    but the client-side check prevents unnecessary processing).

    The `tls_context` is required for production; tests may supply None
    to bypass SSL for in-process testing with a mock processor.
    """

    def __init__(
        self,
        processor: OperationalEventProcessor,
        tls_context: TLSContext | None = None,
    ) -> None:
        self._processor = processor
        self._tls_context = tls_context
        self._seen_event_ids: set[str] = set()

    @property
    def tls_enabled(self) -> bool:
        return self._tls_context is not None

    def submit(self, event: OperationalEvent) -> IngestionResult:
        """Submit one canonical event; returns an IngestionResult."""
        if event.event_id in self._seen_event_ids:
            return IngestionResult(
                event_id=event.event_id,
                accepted=False,
                duplicate=True,
                reason="duplicate event_id in current session",
            )
        self._seen_event_ids.add(event.event_id)
        result = self._processor.process(event)
        return IngestionResult(
            event_id=event.event_id,
            accepted=result.update_result.accepted,
            duplicate=False,
            reason=result.update_result.reason,
        )

    def submit_many(self, events: tuple[OperationalEvent, ...]) -> tuple[IngestionResult, ...]:
        return tuple(self.submit(event) for event in events)

    def reset_session(self) -> None:
        """Clear the seen-event-id set at the start of a new session."""
        self._seen_event_ids.clear()
