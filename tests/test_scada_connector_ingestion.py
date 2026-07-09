"""WP-011-02 OA-077 — secure event ingestion tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _scada_connector_fixtures import connector_stack  # noqa: E402

from services.scada_connector import SCADAConnectorError, TLSContext  # noqa: E402
from services.scada_connector.harness.datasets import CANONICAL_FAULT_EVENT  # noqa: E402


def test_ingestion_accepts_valid_event():
    view, repository, translator, ingestion, _ = connector_stack()
    result_t = translator.translate(CANONICAL_FAULT_EVENT)
    result_i = ingestion.submit(result_t.event)
    assert result_i.accepted is True
    assert result_i.duplicate is False
    assert result_i.event_id == result_t.event.event_id


def test_duplicate_event_id_rejected_without_resubmission():
    _, _, translator, ingestion, _ = connector_stack()
    result_t = translator.translate(CANONICAL_FAULT_EVENT)
    first = ingestion.submit(result_t.event)
    second = ingestion.submit(result_t.event)
    assert first.accepted is True
    assert second.accepted is False
    assert second.duplicate is True
    assert "duplicate" in second.reason


def test_stale_sequence_rejected_by_engine():
    _, _, translator, ingestion, _ = connector_stack()
    r1 = translator.translate(CANONICAL_FAULT_EVENT)
    ingestion.submit(r1.event)
    from services.adms_operational_state import OperationalEvent

    stale = OperationalEvent(
        event_id="test-connector:stale-001",
        event_type="breaker_operation",
        asset_id="e1",
        asset_kind="edge",
        sequence=0,  # stale — less than first submitted
        observed_at="2026-07-09T19:59:00Z",
        actor="test-connector",
        payload={"status": "closed", "available": True},
    )
    result = ingestion.submit(stale)
    assert result.accepted is False
    assert not result.duplicate


def test_session_reset_clears_seen_ids():
    _, _, translator, ingestion, _ = connector_stack()
    r = translator.translate(CANONICAL_FAULT_EVENT)
    first = ingestion.submit(r.event)
    assert first.accepted
    ingestion.reset_session()
    second = ingestion.submit(r.event)
    assert second.duplicate is False


def test_tls_context_validates_paths():
    with pytest.raises(SCADAConnectorError):
        TLSContext(client_cert_path="", client_key_path="/k", ca_cert_path="/c")
    with pytest.raises(SCADAConnectorError):
        TLSContext(client_cert_path="/c", client_key_path="", ca_cert_path="/c")
    with pytest.raises(SCADAConnectorError):
        TLSContext(client_cert_path="/c", client_key_path="/k", ca_cert_path="")


def test_tls_context_is_immutable():
    ctx = TLSContext(client_cert_path="/c", client_key_path="/k", ca_cert_path="/ca")
    with pytest.raises(AttributeError):
        ctx.client_cert_path = "/other"  # type: ignore[misc]


def test_ingestion_client_reports_tls_status():
    _, _, _, ingestion, _ = connector_stack()
    assert ingestion.tls_enabled is False
