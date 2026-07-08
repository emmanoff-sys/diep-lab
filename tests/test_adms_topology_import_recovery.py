"""WP-006-08 Objective 18 ADMS import failure recovery tests."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.persistence import (  # noqa: E402
    SESSION_STATUS_MAPPED,
    SESSION_STATUS_PARSED,
    SESSION_STATUS_PUBLISHED,
    SESSION_STATUS_RECEIVED,
    SESSION_STATUS_RETRY_REQUESTED,
    InMemoryImportPersistenceRepository,
)
from services.adms_topology_import.recovery import (  # noqa: E402
    RECOVERY_STEP,
    AdmsImportRecoveryError,
    FailureRecoveryCoordinator,
    RecoveryRetryPolicy,
)
from services.adms_topology_import.runtime import STEP_MAP, STEP_PARSE, STEP_TRANSPORT  # noqa: E402
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    validate_request,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "recovery-import-001"


def _payload(key: str = IDEMPOTENCY_KEY) -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": key,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "recovery-model-a",
            "model_version": "2026.07.08",
            "created_at": "2026-07-08T00:00:00Z",
        },
        "topology": {
            "nodes": [
                {
                    "external_id": "source-1",
                    "node_type": "substation",
                    "name": "Source 1",
                    "latitude": 9.0765,
                    "longitude": 7.3986,
                    "nominal_kv": 33.0,
                    "phases": "ABC",
                    "metadata": {},
                },
                {
                    "external_id": "load-1",
                    "node_type": "load",
                    "name": "Load 1",
                    "latitude": 9.0770,
                    "longitude": 7.3990,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "external_id": "edge-1",
                    "from_node": "source-1",
                    "to_node": "load-1",
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


def _request(key: str = IDEMPOTENCY_KEY) -> TransportRequest:
    return TransportRequest(
        method="POST",
        scheme="https",
        tls_version="1.2",
        client_certificate_subject="CN=adms-import",
        headers={
            "Authorization": f"Bearer {DEV_BEARER}",
            "Content-Type": "application/json",
            "X-Correlation-ID": CORRELATION_ID,
            "Idempotency-Key": key,
        },
        body=json.dumps(_payload(key)),
    )


def _seed_repository(
    *,
    key: str = IDEMPOTENCY_KEY,
    status: str = SESSION_STATUS_MAPPED,
) -> tuple[InMemoryImportPersistenceRepository, str]:
    repository = InMemoryImportPersistenceRepository()
    transport = validate_request(_request(key), idempotency_store=InMemoryIdempotencyStore())
    session = repository.create_import_session(transport, actor="operator")
    repository.append_history(
        session.session_id,
        step=STEP_TRANSPORT,
        status=SESSION_STATUS_RECEIVED,
        reason="transport_validated",
    )
    repository.record_checkpoint(
        session.session_id,
        step=STEP_TRANSPORT,
        data={"payload_sha256": transport.payload_sha256},
    )
    repository.update_import_session(session.session_id, status=SESSION_STATUS_PARSED)
    repository.append_history(
        session.session_id,
        step=STEP_PARSE,
        status=SESSION_STATUS_PARSED,
        reason="payload_parsed",
    )
    repository.record_checkpoint(
        session.session_id,
        step=STEP_PARSE,
        data={"external_model_id": "recovery-model-a"},
    )
    repository.update_import_session(session.session_id, status=status)
    repository.append_history(
        session.session_id,
        step=STEP_MAP,
        status=status,
        reason="topology_mapped",
    )
    repository.record_checkpoint(
        session.session_id,
        step=STEP_MAP,
        data={"node_count": 2, "edge_count": 1},
    )
    return repository, session.session_id


def test_recovery_retry_policy_allows_retry_with_deterministic_delay():
    policy = RecoveryRetryPolicy(max_attempts=3, base_delay_seconds=2, max_delay_seconds=3)

    first = policy.decision_for(attempt=1, reason_code="job_execution_failed")
    second = policy.decision_for(attempt=2, reason_code="job_execution_failed")
    final = policy.decision_for(attempt=3, reason_code="job_execution_failed")

    assert first.retry_allowed
    assert first.next_attempt == 2
    assert first.delay_seconds == 2
    assert second.retry_allowed
    assert second.delay_seconds == 3
    assert not final.retry_allowed
    assert final.next_attempt == 3


def test_recovery_retry_policy_rejects_non_retryable_reason():
    policy = RecoveryRetryPolicy(max_attempts=3)

    decision = policy.decision_for(attempt=1, reason_code="validation_failed")

    assert not decision.retry_allowed
    assert decision.delay_seconds == 0


def test_request_retry_records_retry_status_history_and_checkpoint():
    repository, session_id = _seed_repository()
    coordinator = FailureRecoveryCoordinator(
        repository=repository,
        retry_policy=RecoveryRetryPolicy(max_attempts=2),
    )

    result = coordinator.request_retry(
        session_id,
        attempt=1,
        reason_code="job_execution_failed",
    )

    assert result.decision.retry_allowed
    assert result.session.status == SESSION_STATUS_RETRY_REQUESTED
    assert result.history is not None
    assert result.history.step == RECOVERY_STEP
    assert result.checkpoint is not None
    assert result.checkpoint.data["next_attempt"] == 2
    assert repository.get_import_session(session_id).status == SESSION_STATUS_RETRY_REQUESTED


def test_recovery_diagnostics_report_latest_checkpoint_and_restorable_state():
    repository, session_id = _seed_repository()
    coordinator = FailureRecoveryCoordinator(repository=repository)

    diagnostics = coordinator.diagnostics(session_id)

    assert diagnostics.session_id == session_id
    assert diagnostics.session_status == SESSION_STATUS_MAPPED
    assert diagnostics.latest_checkpoint_step == STEP_MAP
    assert diagnostics.checkpoint_count == 3
    assert diagnostics.history_count == 3
    assert diagnostics.restorable


def test_rollback_to_latest_checkpoint_restores_checkpoint_status():
    repository, session_id = _seed_repository(status=SESSION_STATUS_MAPPED)
    repository.update_import_session(session_id, status=SESSION_STATUS_RETRY_REQUESTED)
    coordinator = FailureRecoveryCoordinator(repository=repository)

    result = coordinator.rollback_to_latest_checkpoint(session_id)

    assert result.checkpoint.step == STEP_MAP
    assert result.restored_status == SESSION_STATUS_MAPPED
    assert result.session.status == SESSION_STATUS_MAPPED
    assert result.history.reason == "rollback_to_checkpoint:map"
    assert result.recovery_checkpoint.data["restored_status"] == SESSION_STATUS_MAPPED
    assert repository.get_import_session(session_id).status == SESSION_STATUS_MAPPED


def test_rollback_rejects_terminal_session_deterministically():
    repository, session_id = _seed_repository(status=SESSION_STATUS_PUBLISHED)
    coordinator = FailureRecoveryCoordinator(repository=repository)

    with pytest.raises(AdmsImportRecoveryError) as raised:
        coordinator.rollback_to_latest_checkpoint(session_id)

    assert raised.value.reason_code == "terminal_session_not_recoverable"


def test_recovery_rejects_missing_checkpoint_deterministically():
    repository = InMemoryImportPersistenceRepository()
    transport = validate_request(_request(), idempotency_store=InMemoryIdempotencyStore())
    session = repository.create_import_session(transport, actor="operator")
    coordinator = FailureRecoveryCoordinator(repository=repository)

    with pytest.raises(AdmsImportRecoveryError) as raised:
        coordinator.latest_checkpoint(session.session_id)

    assert raised.value.reason_code == "checkpoint_not_found"


def test_recovery_retry_policy_validates_configuration():
    with pytest.raises(AdmsImportRecoveryError) as raised:
        RecoveryRetryPolicy(max_attempts=0)

    assert raised.value.reason_code == "invalid_max_attempts"
