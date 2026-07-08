"""WP-006-07 Objective 6 staging workflow tests."""

from __future__ import annotations

import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import map_topology  # noqa: E402
from services.adms_topology_import.parser import parse_payload  # noqa: E402
from services.adms_topology_import.staging import (  # noqa: E402
    STATUS_CANCELLED,
    STATUS_READY_FOR_PUBLISH,
    STATUS_ROLLBACK_REQUESTED,
    STATUS_ROLLED_BACK,
    STATUS_STAGED,
    AdmsTopologyStagingError,
    cancel_staging,
    complete_rollback,
    create_staged_import,
    derive_staging_id,
    mark_ready_for_publish,
    request_rollback,
    staged_summary,
    transition,
)


def _payload():
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": "11111111-1111-1111-1111-111111111111",
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
                },
                {
                    "external_id": "node-2",
                    "node_type": "bus",
                    "name": "Node 2",
                    "latitude": 9.0768,
                    "longitude": 7.3991,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "external_id": "edge-1",
                    "from_node": "node-1",
                    "to_node": "node-2",
                    "edge_type": "line",
                    "is_switchable": False,
                    "normally_closed": True,
                    "is_closed": True,
                    "rating_kw": 1500,
                    "phases": "ABC",
                    "metadata": {},
                }
            ],
        },
    }


def _mapped():
    return map_topology(parse_payload(_payload()))


def _reason_for(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except AdmsTopologyStagingError as exc:
        return exc.reason_code
    return None


def test_create_staged_import_records_validated_topology():
    staged = create_staged_import(_mapped(), actor="tester")

    assert staged.status == STATUS_STAGED
    assert staged.validation_report.is_valid is True
    assert staged.lifecycle[0].from_status is None
    assert staged.lifecycle[0].to_status == STATUS_STAGED
    assert staged.lifecycle[0].actor == "tester"
    assert staged.topology is not None


def test_derive_staging_id_is_deterministic():
    mapped = _mapped()

    assert derive_staging_id(mapped) == derive_staging_id(mapped)
    assert derive_staging_id(mapped).startswith("stage-")


def test_create_staged_import_allows_explicit_staging_id():
    staged = create_staged_import(_mapped(), staging_id="stage-manual")

    assert staged.staging_id == "stage-manual"


def test_invalid_topology_cannot_be_staged():
    mapped = _mapped()
    invalid_node = {**mapped.nodes[0], "latitude": 91.0}
    invalid = replace(mapped, nodes=(invalid_node, *mapped.nodes[1:]))

    assert _reason_for(create_staged_import, invalid) == "invalid_topology_for_staging"


def test_ready_for_publish_transition_does_not_publish():
    staged = mark_ready_for_publish(create_staged_import(_mapped()))

    assert staged.status == STATUS_READY_FOR_PUBLISH
    assert staged.lifecycle[-1].reason == "validated_for_publish"


def test_cancel_from_staged_is_terminal():
    staged = cancel_staging(create_staged_import(_mapped()), reason="operator cancelled")

    assert staged.status == STATUS_CANCELLED
    assert _reason_for(mark_ready_for_publish, staged) == "invalid_status_transition"


def test_rollback_request_records_reason_and_target_version():
    staged = mark_ready_for_publish(create_staged_import(_mapped()))
    rollback = request_rollback(staged, reason="operator rollback", target_version=7)

    assert rollback.status == STATUS_ROLLBACK_REQUESTED
    assert rollback.rollback_reason == "operator rollback"
    assert rollback.rollback_target_version == 7


def test_rollback_completion_requires_request_first():
    staged = create_staged_import(_mapped())

    assert _reason_for(complete_rollback, staged) == "rollback_not_requested"


def test_complete_rollback_reaches_terminal_state():
    staged = request_rollback(create_staged_import(_mapped()), reason="operator rollback")
    completed = complete_rollback(staged)

    assert completed.status == STATUS_ROLLED_BACK
    assert (
        _reason_for(cancel_staging, completed, reason="late cancel") == "invalid_status_transition"
    )


def test_invalid_transition_is_rejected_deterministically():
    staged = create_staged_import(_mapped())

    assert (
        _reason_for(transition, staged, STATUS_ROLLED_BACK, reason="skip rollback")
        == "invalid_status_transition"
    )


def test_transition_requires_reason():
    staged = create_staged_import(_mapped())

    assert _reason_for(transition, staged, STATUS_READY_FOR_PUBLISH, reason="") == (
        "missing_transition_reason"
    )


def test_rollback_requires_reason_and_valid_target():
    staged = create_staged_import(_mapped())

    assert _reason_for(request_rollback, staged, reason="") == "missing_rollback_reason"
    assert (
        _reason_for(request_rollback, staged, reason="operator rollback", target_version=0)
        == "invalid_rollback_target"
    )


def test_staging_error_exposes_diagnostic_fields():
    staged = create_staged_import(_mapped(), staging_id="stage-1")

    with pytest.raises(AdmsTopologyStagingError) as raised:
        transition(staged, STATUS_ROLLED_BACK, reason="skip rollback")

    error = raised.value
    assert error.category == "staging"
    assert error.reason_code == "invalid_status_transition"
    assert error.description == "Cannot transition staging status from staged to rolled_back"
    assert error.offending_object == "stage-1"
    assert error.location == "status"


def test_staged_summary_contains_status_evidence_only():
    staged = request_rollback(
        mark_ready_for_publish(create_staged_import(_mapped(), staging_id="stage-1")),
        reason="operator rollback",
        target_version=3,
    )

    assert staged_summary(staged) == {
        "staging_id": "stage-1",
        "status": STATUS_ROLLBACK_REQUESTED,
        "source_system": "adms-supplier-a",
        "external_model_id": "model-a",
        "external_model_version": "2026.07.08",
        "node_count": 2,
        "edge_count": 1,
        "rollback_target_version": 3,
        "lifecycle": (STATUS_STAGED, STATUS_READY_FOR_PUBLISH, STATUS_ROLLBACK_REQUESTED),
    }
