"""OA-089 — AMI connector framework integration.

Extends the WP-011-02 connector framework for AMI protocol adapters.
No new lifecycle, health, configuration, or registry infrastructure is
introduced — all framework primitives are inherited from WP-011-02.
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
    "AMIConnectorError",
    "AMIConnectorSession",
    "AbstractConnectorSession",
    "ConnectorConfig",
    "ConnectorHealth",
    "ConnectorLifecycle",
    "ConnectorRegistry",
    "SCADAConnectorError",
    "SessionContext",
]


class AMIConnectorError(SCADAConnectorError):
    """Raised when an AMI connector operation cannot proceed deterministically."""


class AMIConnectorSession(AbstractConnectorSession):
    """Extension point for AMI protocol adapters.

    Subclasses implement `receive_event()` to return the next raw AMI
    event dict from the protocol-specific transport. The framework
    lifecycle, health, configuration, and registry are inherited from
    `AbstractConnectorSession` and WP-011-02 unchanged.
    """

    def receive_event(self) -> dict[str, Any] | None:
        """Return the next raw AMI event dict, or None if no event is ready."""
        raise NotImplementedError  # pragma: no cover
