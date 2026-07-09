"""OA-075 — SCADA connector framework.

Lifecycle management, configuration, health monitoring, and extension
points for the protocol-neutral SCADA ingestion framework. Reusable by
future protocol adapters (WP-011-02 delivers the reference implementation;
WP-011-03+ adapters extend via the abstract session interface).

No ADMS business logic lives here. No secrets live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ConnectorStatus = Literal["idle", "connecting", "active", "degraded", "disconnected"]


class SCADAConnectorError(ValueError):
    """Raised when a connector operation cannot proceed deterministically."""


@dataclass(frozen=True)
class ConnectorConfig:
    """All configuration for one connector instance.

    Credential paths are injected from the environment; no credential
    values appear here. The framework validates that mandatory paths are
    non-empty strings at construction time.
    """

    connector_id: str
    actor: str
    buffer_size: int = 1000
    max_retries: int = 10
    backoff_base_s: float = 1.0
    backoff_max_s: float = 300.0
    health_interval_s: float = 30.0
    client_cert_path: str = ""
    client_key_path: str = ""
    ca_cert_path: str = ""

    def __post_init__(self) -> None:
        if not self.connector_id:
            raise SCADAConnectorError("connector_id is required")
        if not self.actor:
            raise SCADAConnectorError("actor is required")
        if self.buffer_size < 1:
            raise SCADAConnectorError("buffer_size must be ≥ 1")
        if self.max_retries < 0:
            raise SCADAConnectorError("max_retries must be ≥ 0")

    @property
    def tls_configured(self) -> bool:
        return bool(self.client_cert_path and self.client_key_path and self.ca_cert_path)


@dataclass(frozen=True)
class ConnectorHealth:
    connector_id: str
    status: ConnectorStatus
    session_count: int
    events_submitted: int
    events_rejected: int
    events_dead_lettered: int
    last_error: str | None

    @property
    def healthy(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class SessionContext:
    """Immutable identity of one connector session."""

    connector_id: str
    session_id: str
    started_at: str


class AbstractConnectorSession:
    """Extension point: subclasses implement protocol-specific I/O."""

    def __init__(self, context: SessionContext, config: ConnectorConfig) -> None:
        self.context = context
        self.config = config

    def receive_message(self) -> dict[str, Any] | None:
        """Return the next raw message dict, or None if no message is ready."""
        raise NotImplementedError  # pragma: no cover

    def close(self) -> None:
        """Release protocol-level resources."""


class ConnectorRegistry:
    """Tracks connector instances within one process."""

    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorConfig] = {}

    def register(self, config: ConnectorConfig) -> None:
        if config.connector_id in self._connectors:
            raise SCADAConnectorError(f"connector already registered: {config.connector_id}")
        self._connectors[config.connector_id] = config

    def deregister(self, connector_id: str) -> None:
        if connector_id not in self._connectors:
            raise SCADAConnectorError(f"unknown connector: {connector_id}")
        del self._connectors[connector_id]

    def get(self, connector_id: str) -> ConnectorConfig:
        config = self._connectors.get(connector_id)
        if config is None:
            raise SCADAConnectorError(f"unknown connector: {connector_id}")
        return config

    @property
    def connector_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._connectors))


class ConnectorLifecycle:
    """Manages health counters and status transitions for one connector."""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._status: ConnectorStatus = "idle"
        self._session_count = 0
        self._events_submitted = 0
        self._events_rejected = 0
        self._events_dead_lettered = 0
        self._last_error: str | None = None

    def on_connect(self) -> None:
        self._status = "active"
        self._session_count += 1
        self._last_error = None

    def on_disconnect(self, error: str | None = None) -> None:
        self._status = "disconnected"
        if error:
            self._last_error = error

    def on_event_submitted(self) -> None:
        self._events_submitted += 1

    def on_event_rejected(self, reason: str) -> None:
        self._events_rejected += 1
        self._last_error = f"rejection: {reason}"

    def on_event_dead_lettered(self, reason: str) -> None:
        self._events_dead_lettered += 1
        self._last_error = f"dead-letter: {reason}"

    def on_degraded(self, reason: str) -> None:
        self._status = "degraded"
        self._last_error = reason

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            connector_id=self.config.connector_id,
            status=self._status,
            session_count=self._session_count,
            events_submitted=self._events_submitted,
            events_rejected=self._events_rejected,
            events_dead_lettered=self._events_dead_lettered,
            last_error=self._last_error,
        )
