"""WP-011-03 OA-082 — GIS connector framework integration tests."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.gis_connector import (  # noqa: E402
    ConnectorConfig,
    ConnectorHealth,
    ConnectorLifecycle,
    ConnectorRegistry,
    GISConnectorError,
    GISConnectorSession,
    SCADAConnectorError,
    SessionContext,
)
from services.scada_connector.framework import AbstractConnectorSession  # noqa: E402

_GIS_CONFIG = ConnectorConfig(connector_id="test-gis-01", actor="test-gis-connector")


def test_gis_connector_session_extends_abstract_session():
    assert issubclass(GISConnectorSession, AbstractConnectorSession)


def test_gis_connector_error_extends_scada_connector_error():
    assert issubclass(GISConnectorError, SCADAConnectorError)


def test_connector_config_validates_required_fields():
    import pytest

    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="", actor="a")
    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="gis", actor="")


def test_connector_config_tls_detection():
    bare = ConnectorConfig(connector_id="gis", actor="a")
    assert not bare.tls_configured
    tls = ConnectorConfig(
        connector_id="gis",
        actor="a",
        client_cert_path="/certs/gis-client.crt",
        client_key_path="/certs/gis-client.key",
        ca_cert_path="/certs/ca.crt",
    )
    assert tls.tls_configured


def test_connector_registry_register_and_deregister():
    registry = ConnectorRegistry()
    registry.register(_GIS_CONFIG)
    assert _GIS_CONFIG.connector_id in registry.connector_ids
    assert registry.get(_GIS_CONFIG.connector_id) is _GIS_CONFIG
    registry.deregister(_GIS_CONFIG.connector_id)
    assert _GIS_CONFIG.connector_id not in registry.connector_ids


def test_registry_duplicate_registration_rejected():
    import pytest

    registry = ConnectorRegistry()
    registry.register(_GIS_CONFIG)
    with pytest.raises(SCADAConnectorError):
        registry.register(_GIS_CONFIG)


def test_lifecycle_health_transitions():
    lifecycle = ConnectorLifecycle(_GIS_CONFIG)
    assert lifecycle.health().status == "idle"
    assert not lifecycle.health().healthy
    lifecycle.on_connect()
    h = lifecycle.health()
    assert h.status == "active"
    assert h.healthy
    assert h.session_count == 1
    lifecycle.on_event_submitted()
    lifecycle.on_event_rejected("topology import rejected")
    h2 = lifecycle.health()
    assert h2.events_submitted == 1
    assert h2.events_rejected == 1
    assert "topology import rejected" in h2.last_error


def test_lifecycle_degraded_and_disconnect():
    lifecycle = ConnectorLifecycle(_GIS_CONFIG)
    lifecycle.on_connect()
    lifecycle.on_degraded("GIS unavailable")
    assert lifecycle.health().status == "degraded"
    lifecycle.on_disconnect(error="GIS connection lost")
    h = lifecycle.health()
    assert h.status == "disconnected"
    assert "GIS connection lost" in h.last_error


def test_session_context_is_immutable():
    import pytest

    ctx = SessionContext(
        connector_id="gis-01", session_id="s-001", started_at="2026-07-09T20:00:00Z"
    )
    with pytest.raises(AttributeError):
        ctx.connector_id = "x"  # type: ignore[misc]


def test_gis_connector_session_fetch_topology_raises_not_implemented():
    import pytest

    ctx = SessionContext(
        connector_id="gis-01", session_id="s-001", started_at="2026-07-09T20:00:00Z"
    )

    class _Stub(GISConnectorSession):
        pass

    session = _Stub(ctx, _GIS_CONFIG)
    with pytest.raises(NotImplementedError):
        session.fetch_topology()


def test_connector_health_dataclass_fields():
    health = ConnectorHealth(
        connector_id="gis-01",
        status="active",
        session_count=1,
        events_submitted=5,
        events_rejected=0,
        events_dead_lettered=0,
        last_error=None,
    )
    assert health.healthy
    assert health.connector_id == "gis-01"
