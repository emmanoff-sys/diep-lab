"""WP-011-04 OA-092 — secure AMI event ingestion tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _scada_connector_fixtures import connector_stack  # noqa: E402

from services.ami_connector import (  # noqa: E402
    AMIEventTranslator,
    AMIIngestionAdapter,
    AMIIngestionRecord,
    AMIMeterIdentityMap,
)
from services.ami_connector.harness import (  # noqa: E402
    AMI_CANONICAL_METER_MAP,
    AMI_LAST_GASP_EVENT,
    AMI_METER_READING_EVENT,
)
from services.scada_connector import TLSContext  # noqa: E402
from services.scada_connector.framework import SCADAConnectorError  # noqa: E402


def _ami_stack():
    view, repository, _, ingestion_client, _ = connector_stack()
    meter_map = AMIMeterIdentityMap(AMI_CANONICAL_METER_MAP)
    translator = AMIEventTranslator(meter_map, actor="ami-connector-test")
    adapter = AMIIngestionAdapter(ingestion_client)
    return view, repository, translator, adapter


def test_ingestion_accepts_last_gasp_event():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_LAST_GASP_EVENT)
    assert result_t.success
    record = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    assert isinstance(record, AMIIngestionRecord)
    assert record.accepted is True
    assert record.duplicate is False
    assert record.meter_id == AMI_LAST_GASP_EVENT.meter_id


def test_ingestion_accepts_telemetry_event():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_METER_READING_EVENT)
    record = adapter.submit(AMI_METER_READING_EVENT.meter_id, result_t.event)
    assert record.accepted is True
    assert record.event_id == result_t.event.event_id


def test_duplicate_event_id_rejected():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_LAST_GASP_EVENT)
    first = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    second = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    assert first.accepted is True
    assert second.accepted is False
    assert second.duplicate is True


def test_meter_id_correlated_on_duplicate():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_LAST_GASP_EVENT)
    adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    dup = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    assert dup.meter_id == AMI_LAST_GASP_EVENT.meter_id


def test_session_reset_clears_seen_ids():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_LAST_GASP_EVENT)
    first = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    assert first.accepted
    adapter.reset_session()
    second = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    assert second.duplicate is False


def test_tls_disabled_by_default():
    _, _, _, adapter = _ami_stack()
    assert adapter.tls_enabled is False


def test_tls_context_validates_paths():
    with pytest.raises(SCADAConnectorError):
        TLSContext(client_cert_path="", client_key_path="/k", ca_cert_path="/c")


def test_submit_many_length_mismatch_raises():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_LAST_GASP_EVENT)
    with pytest.raises(ValueError, match="must match"):
        adapter.submit_many(
            ("AMI:METER-C-001", "AMI:METER-C-002"),
            (result_t.event,),
        )


def test_submit_many_returns_all_records():
    _, _, translator, adapter = _ami_stack()
    r1 = translator.translate(AMI_LAST_GASP_EVENT)
    r2 = translator.translate(AMI_METER_READING_EVENT)
    records = adapter.submit_many(
        (AMI_LAST_GASP_EVENT.meter_id, AMI_METER_READING_EVENT.meter_id),
        (r1.event, r2.event),
    )
    assert len(records) == 2
    assert all(isinstance(r, AMIIngestionRecord) for r in records)


def test_ingestion_record_is_frozen():
    _, _, translator, adapter = _ami_stack()
    result_t = translator.translate(AMI_LAST_GASP_EVENT)
    record = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result_t.event)
    with pytest.raises(AttributeError):
        record.accepted = False  # type: ignore[misc]
