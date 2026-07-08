"""WP-006-07 Objective 8 observability tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import map_topology  # noqa: E402
from services.adms_topology_import.metrics import AdmsImportMetrics, _NoOpMetric  # noqa: E402
from services.adms_topology_import.observability import (  # noqa: E402
    AdmsObservabilityError,
    audit_lifecycle_event,
    correlation_for_staged,
    correlation_from_transport,
    deterministic_audit_event_id,
    health_snapshot,
    record_lifecycle_metrics,
    record_validation_metrics,
    structured_log_event,
)
from services.adms_topology_import.parser import parse_payload  # noqa: E402
from services.adms_topology_import.staging import create_staged_import  # noqa: E402
from services.adms_topology_import.transport import TransportRequest, validate_request  # noqa: E402
from services.adms_topology_import.validation import validate_topology  # noqa: E402

CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


def _payload():
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": "import-001",
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "model-a",
            "model_version": "2026.07.08",
            "created_at": "2026-07-08T00:00:00Z",
        },
        "topology": {
            "nodes": [
                {
                    "external_id": "node-1",
                    "node_type": "bus",
                    "name": "Node 1",
                    "latitude": 9.0765,
                    "longitude": 7.3986,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {},
                }
            ],
            "edges": [],
        },
    }


def _staged():
    return create_staged_import(map_topology(parse_payload(_payload())), staging_id="stage-1")


def test_correlation_context_from_transport_result():
    result = validate_request(
        TransportRequest(
            method="POST",
            scheme="https",
            tls_version="1.2",
            headers={
                "Authorization": "Bearer diep-adms-import-dev-token-CHANGE-ME",
                "Content-Type": "application/json",
                "X-Correlation-ID": CORRELATION_ID,
                "Idempotency-Key": "import-001",
            },
            body="{}",
        )
    )

    context = correlation_from_transport(result)

    assert context.correlation_id == CORRELATION_ID
    assert context.idempotency_key == "import-001"


def test_correlation_context_for_staged_import():
    context = correlation_for_staged(
        _staged(),
        correlation_id=CORRELATION_ID,
        idempotency_key="import-001",
    )

    assert context.staging_id == "stage-1"
    assert context.external_model_id == "model-a"
    assert context.external_model_version == "2026.07.08"


def test_structured_log_event_contains_trace_fields():
    context = correlation_for_staged(_staged(), correlation_id=CORRELATION_ID)

    event = structured_log_event("adms.import.staged", context=context, status="staged")

    assert event["event"] == "adms.import.staged"
    assert event["service"] == "adms-topology-import"
    assert event["correlation_id"] == CORRELATION_ID
    assert event["staging_id"] == "stage-1"
    assert event["status"] == "staged"


def test_structured_log_event_requires_name():
    context = correlation_for_staged(_staged(), correlation_id=CORRELATION_ID)

    with pytest.raises(AdmsObservabilityError) as raised:
        structured_log_event("", context=context)

    assert raised.value.reason_code == "missing_log_event"
    assert raised.value.location == "event"


def test_audit_lifecycle_event_contains_staging_evidence():
    event = audit_lifecycle_event(
        _staged(),
        correlation_id=CORRELATION_ID,
        action="topology_import.stage",
        metadata={"operator": "engineer"},
    )

    assert event.event_type == "adms.topology_import.staged"
    assert event.action == "topology_import.stage"
    assert event.resource_type == "topology_import"
    assert event.resource_id == "stage-1"
    assert event.correlation_id == CORRELATION_ID
    assert event.metadata["external_model_id"] == "model-a"
    assert event.metadata["operator"] == "engineer"


def test_audit_event_id_is_deterministic():
    event = audit_lifecycle_event(
        _staged(),
        correlation_id=CORRELATION_ID,
        action="topology_import.stage",
    )

    assert deterministic_audit_event_id(event) == deterministic_audit_event_id(event)


def test_audit_lifecycle_event_requires_correlation_id():
    with pytest.raises(AdmsObservabilityError) as raised:
        audit_lifecycle_event(_staged(), correlation_id="", action="topology_import.stage")

    assert raised.value.reason_code == "missing_correlation_id"


def test_metrics_holder_exposes_objective_eight_instruments():
    metrics = AdmsImportMetrics(enabled=False)

    assert isinstance(metrics.lifecycle_events_total, _NoOpMetric)
    assert isinstance(metrics.validation_failures_total, _NoOpMetric)
    assert isinstance(metrics.staged_imports_gauge, _NoOpMetric)


def test_metric_recorders_are_noop_safe():
    metrics = AdmsImportMetrics(enabled=False)
    invalid = _staged().topology
    invalid.nodes[0]["latitude"] = 91.0
    report = validate_topology(invalid)

    record_lifecycle_metrics(metrics, status="staged")
    record_validation_metrics(metrics, report)


def test_health_snapshot_contains_operational_diagnostics():
    snapshot = health_snapshot(metrics_enabled=True, ready=False, detail="warming")

    assert snapshot["service"] == "adms-topology-import"
    assert snapshot["metrics_enabled"] is True
    assert snapshot["ready"] is False
    assert snapshot["detail"] == "warming"
    assert snapshot["checked_at"].endswith("+00:00")
