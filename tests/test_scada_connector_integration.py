"""WP-011-02 OA-080/081 — SCADA connector integration tests.

Drives the full path from canonical stub → translation → OperationalEvent
→ WP-008 ingestion → WP-009 detection → WP-010 assessment, plus
regression guards for Phase 1 layers.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _adms_operations_fixtures import operations_stack  # noqa: E402
from _scada_connector_fixtures import (  # noqa: E402
    asset_map,
    connector_stack,
    full_pipeline,
    make_processor,
)

from services.adms_operational_intelligence import OperationalIntelligenceService  # noqa: E402
from services.adms_operations import OutageDetectionService  # noqa: E402
from services.adms_topology_services import OutageImpactService  # noqa: E402
from services.scada_connector import IngestionClient, SCADAEventTranslator  # noqa: E402
from services.scada_connector.harness import (  # noqa: E402
    CANONICAL_FAULT_EVENT,
    TWO_FEEDER_TOPOLOGY,
    ScadaStub,
    SessionRecorder,
    SessionReplayer,
    make_scada_messages,
    validate_operational_event,
)
from services.scada_connector.harness.contracts import validate_mapped_topology  # noqa: E402


def test_stub_to_detection_end_to_end():
    """SCADA stub → translate → ingest → WP-009 detects outage."""
    view, repository, translator, ingestion, _ = connector_stack()
    stub = ScadaStub(
        (
            {
                "message_id": CANONICAL_FAULT_EVENT.message_id,
                "external_asset_id": CANONICAL_FAULT_EVENT.external_asset_id,
                "message_type": CANONICAL_FAULT_EVENT.message_type,
                "observed_at": CANONICAL_FAULT_EVENT.observed_at,
                "sequence": CANONICAL_FAULT_EVENT.sequence,
                "raw_payload": dict(CANONICAL_FAULT_EVENT.raw_payload),
            },
        )
    )
    raw = stub.next_message()
    from services.scada_connector import SCADAMessage

    msg = SCADAMessage(**raw)
    result = translator.translate(msg)
    validate_operational_event(result.event)
    ingestion_result = ingestion.submit(result.event)
    assert ingestion_result.accepted
    groups = OutageDetectionService(view).detect_all()
    assert len(groups) == 1
    assert groups[0].affected_nodes == ("a", "b", "c")


def test_full_pipeline_to_intelligence():
    """Pipeline → WP-010 assessment includes fault_candidates."""
    _, repository, pipeline = full_pipeline()
    from _scada_connector_fixtures import full_pipeline as fp

    view, repository, pipeline = fp()
    pipeline.enqueue(CANONICAL_FAULT_EVENT)
    pipeline.process_buffered()
    assert pipeline.results[0].accepted
    group = OutageDetectionService(view).detect_all()[0]
    assessment = OperationalIntelligenceService(view).assess(group)
    assert assessment.fault_report.candidates[0].edge_id == "e1"
    assert assessment.strategies[0].candidate.tie_edge_id == "tie1"


def test_connector_is_read_only_no_control_output():
    """Verify the connector produces no control output — only OperationalEvents submitted to ingestion."""
    view, repository, translator, ingestion, _ = connector_stack()
    result = translator.translate(CANONICAL_FAULT_EVENT)
    assert result.event.event_type in ("breaker_operation", "alarm", "telemetry")
    assert not hasattr(result.event, "command")
    assert not hasattr(result.event, "write_back")
    assert not hasattr(result.event, "control_action")


def test_session_replay_produces_identical_outcome():
    """Same session replayed twice gives identical post-ingestion state."""

    def run_once():
        view, repository = operations_stack()
        processor = make_processor(view, repository)
        identity_map = asset_map()
        translator = SCADAEventTranslator(identity_map, actor="test-connector")
        ingestion = IngestionClient(processor)
        msg = CANONICAL_FAULT_EVENT
        result = translator.translate(msg)
        ingestion.submit(result.event)
        return repository.get_state("e1", asset_kind="edge")

    state_a = run_once()
    state_b = run_once()
    assert state_a == state_b


def test_untranslatable_messages_do_not_block_valid_messages():
    _, _, pipeline = full_pipeline()
    bad = make_scada_messages(
        ("UNKNOWN-ASSET", "status_change", 1, {"status": "open", "available": False})
    )
    pipeline.enqueue(bad[0])
    pipeline.enqueue(CANONICAL_FAULT_EVENT)
    pipeline.process_buffered()
    assert pipeline.dead_letter_queue.count == 1
    assert any(r.accepted for r in pipeline.results)


def test_gis_topology_contract_satisfied_by_canonical_dataset():
    """The canonical two-feeder topology satisfies MappedTopology v1.0."""
    validate_mapped_topology(TWO_FEEDER_TOPOLOGY)
    assert TWO_FEEDER_TOPOLOGY.source_system == "scada-connector-test"


def test_phase1_regression_wp007_and_wp008():
    """WP-007 topology and WP-008 state unaffected by connector operation."""
    view, repository, translator, ingestion, _ = connector_stack()
    translator.translate(CANONICAL_FAULT_EVENT)
    ingestion.submit(translator.translate(CANONICAL_FAULT_EVENT).event)
    impact = OutageImpactService(view.topology).analyze_edge_outage("e2")
    assert "c" in impact.affected_nodes
    assert impact.customer_count >= 40
    ingestion.submit(translator.translate(CANONICAL_FAULT_EVENT).event)
    history = repository.history("e1")
    assert len(history) == 1
