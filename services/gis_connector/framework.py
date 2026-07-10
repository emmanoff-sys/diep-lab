"""OA-082 — GIS connector framework integration.

Extends the WP-011-02 connector framework with GIS-specific session
behaviour. All lifecycle, health, configuration, and registry primitives
are inherited unchanged from services.scada_connector.framework; only
the session I/O is specialised for batch topology fetches.

No ADMS business logic lives here. No secrets live here.
"""

from __future__ import annotations

from typing import Any

from services.scada_connector.framework import (
    AbstractConnectorSession,
    ConnectorConfig,
    ConnectorHealth,
    ConnectorLifecycle,
    ConnectorRegistry,
    SCADAConnectorError,
    SessionContext,
)

__all__ = [
    "AbstractConnectorSession",
    "ConnectorConfig",
    "ConnectorHealth",
    "ConnectorLifecycle",
    "ConnectorRegistry",
    "GISConnectorError",
    "GISConnectorSession",
    "SCADAConnectorError",
    "SessionContext",
]


class GISConnectorError(SCADAConnectorError):
    """Raised when a GIS connector operation cannot proceed deterministically."""


class GISConnectorSession(AbstractConnectorSession):
    """Extension point for GIS topology batch fetch sessions.

    Subclasses implement `fetch_topology()` to return a raw GIS topology
    batch dict from the GIS platform. Topology is fetched as a complete
    model snapshot, not a stream of messages; `receive_message()` is not
    the appropriate interface for GIS adapters.
    """

    def fetch_topology(self) -> dict[str, Any] | None:
        """Return a raw GIS topology batch dict, or None if unavailable."""
        raise NotImplementedError  # pragma: no cover
