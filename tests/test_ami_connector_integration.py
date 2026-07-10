"""WP-011-04 OA-094 — AMI connector integration tests.

Drives the full path from AmiStub → identity resolution → event
translation → ingestion → contract validation, plus regression guards
for Phase 1 and EPIC-011 layers.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402
from _scada_connector_fixtures import connector_stack  # noqa: E402

from services.adms_topology_services import OutageImpactService  # noqa: E402
from services.ami_connector import (  # noqa: E402
    AMIEventTranslator,
    AMIIngestionAdapter,
    AMIMeterIdentityMap,
)
from services.ami_connector.harness import (  # noqa: E402
    AMI_CANONICAL_BATCH,
    AMI_CANONICAL_METER_MAP,
    AMI_LAST_GASP_EVENT,
    AMI_METER_READING_EVENT,
    AmiStub,
)
from services.scada_connector.harness.contracts import validate_operational_event  # noqa: E402

_METER_MAP = AMIMeterIdentityMap(AMI_CANONICAL_METER_MAP)
_ACTOR = "ami-connector-integration-test"


def _full_stack():
    view, repository, _, ingestion_client, _ = connector_stack()
    meter_map = AMIMeterIdentityMap(AMI_CANONICAL_METER_MAP)
    translator = AMIEventTranslator(meter_map, actor=_ACTOR)
    adapter = AMIIngestionAdapter(ingestion_client)
    return view, repository, translator, adapter


def test_stub_to_canonical_event_end_to_end():
    """AmiStub → translate → canonical OperationalEvent satisfies contract."""
    _, _, translator, _ = _full_stack()
    result = translator.translate(AMI_LAST_GASP_EVENT)
    assert result.success
    validate_operational_event(result.event)


def test_stub_to_ingestion_end_to_end():
    """AmiStub → translate → submit → accepted by ingestion pipeline."""
    _, _, translator, adapter = _full_stack()
    result = translator.translate(AMI_LAST_GASP_EVENT)
    record = adapter.submit(AMI_LAST_GASP_EVENT.meter_id, result.event)
    assert record.accepted is True
    assert record.meter_id == AMI_LAST_GASP_EVENT.meter_id


def test_full_batch_all_accepted():
    """All four canonical batch events are accepted by the pipeline."""
    _, _, translator, adapter = _full_stack()
    for msg in AMI_CANONICAL_BATCH:
        r = translator.translate(msg)
        assert r.success, f"translation failed for {msg.message_id}"
        record = adapter.submit(msg.meter_id, r.event)
        assert record.accepted, f"ingestion rejected {msg.message_id}: {record.reason}"


def test_ami_connector_produces_no_control_output():
    """Translated AMI events carry no meter control payload fields."""
    _, _, translator, _ = _full_stack()
    for msg in AMI_CANONICAL_BATCH:
        r = translator.translate(msg)
        assert r.success
        assert "disconnect" not in r.event.payload
        assert "reconnect" not in r.event.payload
        assert "command" not in r.event.payload
        assert "firmware" not in r.event.payload
        assert "config" not in r.event.payload


def test_ami_connector_is_read_only_no_control_methods():
    """AMI connector exposes no meter control, disconnect, or command surfaces."""
    _, _, translator, _ = _full_stack()
    result = translator.translate(AMI_LAST_GASP_EVENT)
    event = result.event
    assert not hasattr(event, "disconnect")
    assert not hasattr(event, "reconnect")
    assert not hasattr(event, "configure_meter")
    assert not hasattr(event, "firmware_update")
    assert not hasattr(event, "command")
    assert not hasattr(event, "control_action")


def test_stub_from_messages_integration():
    """AmiStub.from_messages drives the translate+submit path deterministically."""
    _, _, translator, adapter = _full_stack()
    stub = AmiStub.from_messages(AMI_CANONICAL_BATCH)
    accepted_count = 0
    while not stub.exhausted:
        raw = stub.next_event()
        if raw:
            from services.ami_connector.translation import AMIMessage

            msg = AMIMessage(
                message_id=raw["message_id"],
                meter_id=raw["meter_id"],
                message_type=raw["message_type"],
                observed_at=raw["observed_at"],
                sequence=raw["sequence"],
                raw_payload=raw["raw_payload"],
            )
            r = translator.translate(msg)
            if r.success:
                rec = adapter.submit(msg.meter_id, r.event)
                if rec.accepted:
                    accepted_count += 1
    assert accepted_count == 4


def test_regression_wp007_topology_unaffected():
    """WP-007 topology service unaffected by AMI connector operation."""
    view, _ = operations_stack()
    translator = AMIEventTranslator(_METER_MAP, actor=_ACTOR)
    translator.translate(AMI_LAST_GASP_EVENT)
    impact = OutageImpactService(view.topology).analyze_edge_outage("e2")
    assert "c" in impact.affected_nodes
    assert impact.customer_count >= 40


def test_regression_phase1_adms_stack_intact():
    """Phase 1 ADMS operational stack unchanged by AMI connector operation."""
    view, _ = operations_stack()
    translator = AMIEventTranslator(_METER_MAP, actor=_ACTOR)
    for msg in AMI_CANONICAL_BATCH:
        translator.translate(msg)
    node_ids = {n.node_id for n in view.topology.nodes}
    assert "f1" in node_ids
    assert "e1" in {e.edge_id for e in view.topology.edges}


def test_regression_scada_connector_still_accepts_events():
    """SCADA connector ingestion pipeline unaffected by AMI connector operation."""
    _, _, scada_translator, scada_ingestion, _ = connector_stack()
    from services.scada_connector.harness.datasets import CANONICAL_FAULT_EVENT

    r = scada_translator.translate(CANONICAL_FAULT_EVENT)
    result = scada_ingestion.submit(r.event)
    assert result.accepted is True


def test_ami_telemetry_does_not_conflict_with_scada_events():
    """AMI telemetry event and SCADA breaker event coexist in the pipeline."""
    _, _, scada_translator, scada_ingestion, _ = connector_stack()
    ami_translator = AMIEventTranslator(_METER_MAP, actor=_ACTOR)
    adapter = AMIIngestionAdapter(scada_ingestion)

    from services.scada_connector.harness.datasets import CANONICAL_FAULT_EVENT

    scada_r = scada_translator.translate(CANONICAL_FAULT_EVENT)
    scada_ingestion.submit(scada_r.event)

    ami_r = ami_translator.translate(AMI_METER_READING_EVENT)
    ami_record = adapter.submit(AMI_METER_READING_EVENT.meter_id, ami_r.event)
    assert ami_record.accepted is True


def test_lifecycle_tracks_ami_event_submissions():
    """ConnectorLifecycle tracks AMI event submissions correctly."""
    from services.ami_connector import ConnectorConfig, ConnectorLifecycle

    cfg = ConnectorConfig(connector_id="ami-int-01", actor="ami-connector-integration")
    lc = ConnectorLifecycle(cfg)
    lc.on_connect()
    for _ in AMI_CANONICAL_BATCH:
        lc.on_event_submitted()
    assert lc.health().events_submitted == len(AMI_CANONICAL_BATCH)
    assert lc.health().healthy is True
