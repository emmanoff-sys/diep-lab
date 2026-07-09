"""WP-011-02 OA-075 — SCADA connector framework tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _scada_connector_fixtures import DEFAULT_CONFIG  # noqa: E402

from services.scada_connector import (  # noqa: E402
    ConnectorConfig,
    ConnectorLifecycle,
    ConnectorRegistry,
    SCADAConnectorError,
    SessionContext,
)


def test_config_validates_required_fields():
    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="", actor="a")
    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="c", actor="")
    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="c", actor="a", buffer_size=0)


def test_config_tls_detection():
    bare = ConnectorConfig(connector_id="c", actor="a")
    assert not bare.tls_configured
    tls = ConnectorConfig(
        connector_id="c",
        actor="a",
        client_cert_path="/certs/client.crt",
        client_key_path="/certs/client.key",
        ca_cert_path="/certs/ca.crt",
    )
    assert tls.tls_configured


def test_registry_register_and_deregister():
    registry = ConnectorRegistry()
    registry.register(DEFAULT_CONFIG)
    assert DEFAULT_CONFIG.connector_id in registry.connector_ids
    assert registry.get(DEFAULT_CONFIG.connector_id) is DEFAULT_CONFIG
    registry.deregister(DEFAULT_CONFIG.connector_id)
    assert DEFAULT_CONFIG.connector_id not in registry.connector_ids


def test_registry_duplicate_registration_rejected():
    registry = ConnectorRegistry()
    registry.register(DEFAULT_CONFIG)
    with pytest.raises(SCADAConnectorError):
        registry.register(DEFAULT_CONFIG)


def test_registry_unknown_get_and_deregister_raise():
    registry = ConnectorRegistry()
    with pytest.raises(SCADAConnectorError):
        registry.get("unknown")
    with pytest.raises(SCADAConnectorError):
        registry.deregister("unknown")


def test_lifecycle_health_transitions():
    lifecycle = ConnectorLifecycle(DEFAULT_CONFIG)
    assert lifecycle.health().status == "idle"
    assert not lifecycle.health().healthy
    lifecycle.on_connect()
    h = lifecycle.health()
    assert h.status == "active"
    assert h.healthy
    assert h.session_count == 1
    assert h.last_error is None
    lifecycle.on_event_submitted()
    lifecycle.on_event_submitted()
    lifecycle.on_event_rejected("stale sequence")
    h2 = lifecycle.health()
    assert h2.events_submitted == 2
    assert h2.events_rejected == 1
    assert "stale sequence" in h2.last_error


def test_lifecycle_degraded_and_disconnect():
    lifecycle = ConnectorLifecycle(DEFAULT_CONFIG)
    lifecycle.on_connect()
    lifecycle.on_degraded("rejection threshold exceeded")
    assert lifecycle.health().status == "degraded"
    lifecycle.on_disconnect(error="connection lost")
    h = lifecycle.health()
    assert h.status == "disconnected"
    assert "connection lost" in h.last_error


def test_session_context_is_immutable():
    ctx = SessionContext(connector_id="c", session_id="s-001", started_at="2026-07-09T20:00:00Z")
    with pytest.raises(AttributeError):
        ctx.connector_id = "x"  # type: ignore[misc]
