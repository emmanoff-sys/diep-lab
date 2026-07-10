"""WP-011-04 OA-089 — AMI connector framework tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ami_connector import (  # noqa: E402
    AMIConnectorError,
    AMIConnectorSession,
    ConnectorConfig,
    ConnectorHealth,
    ConnectorLifecycle,
    ConnectorRegistry,
    SCADAConnectorError,
    SessionContext,
)
from services.scada_connector.framework import AbstractConnectorSession  # noqa: E402

_CFG = ConnectorConfig(connector_id="ami-adapter-01", actor="ami-connector")


def test_ami_connector_session_extends_abstract():
    assert issubclass(AMIConnectorSession, AbstractConnectorSession)


def test_ami_connector_error_extends_scada_error():
    assert issubclass(AMIConnectorError, SCADAConnectorError)


def test_connector_config_requires_connector_id():
    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="", actor="ami-connector")


def test_connector_config_requires_actor():
    with pytest.raises(SCADAConnectorError):
        ConnectorConfig(connector_id="ami-01", actor="")


def test_connector_config_tls_not_configured_by_default():
    assert _CFG.tls_configured is False


def test_connector_config_tls_configured_with_all_paths():
    cfg = ConnectorConfig(
        connector_id="ami-01",
        actor="ami-connector",
        client_cert_path="/c",
        client_key_path="/k",
        ca_cert_path="/ca",
    )
    assert cfg.tls_configured is True


def test_lifecycle_starts_idle():
    lc = ConnectorLifecycle(_CFG)
    assert lc.health().status == "idle"


def test_lifecycle_on_connect_transitions_to_active():
    lc = ConnectorLifecycle(_CFG)
    lc.on_connect()
    assert lc.health().status == "active"
    assert lc.health().healthy is True


def test_lifecycle_tracks_event_submissions():
    lc = ConnectorLifecycle(_CFG)
    lc.on_connect()
    lc.on_event_submitted()
    lc.on_event_submitted()
    lc.on_event_submitted()
    assert lc.health().events_submitted == 3


def test_registry_register_and_retrieve():
    reg = ConnectorRegistry()
    reg.register(_CFG)
    assert _CFG.connector_id in reg.connector_ids
    assert reg.get(_CFG.connector_id).actor == "ami-connector"


def test_registry_duplicate_registration_raises():
    reg = ConnectorRegistry()
    reg.register(_CFG)
    with pytest.raises(SCADAConnectorError, match="already registered"):
        reg.register(_CFG)


def test_session_context_is_frozen():
    ctx = SessionContext(
        connector_id="ami-01",
        session_id="s-001",
        started_at="2026-07-10T06:00:00Z",
    )
    with pytest.raises(AttributeError):
        ctx.session_id = "other"  # type: ignore[misc]


def test_ami_connector_health_reports_correct_connector_id():
    lc = ConnectorLifecycle(_CFG)
    assert lc.health().connector_id == "ami-adapter-01"


def test_connector_health_is_frozen():
    h = ConnectorHealth(
        connector_id="ami-01",
        status="active",
        session_count=1,
        events_submitted=0,
        events_rejected=0,
        events_dead_lettered=0,
        last_error=None,
    )
    with pytest.raises(AttributeError):
        h.status = "idle"  # type: ignore[misc]
