"""WP-006-08 Objective 12 ADMS import persistence tests."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import map_topology  # noqa: E402
from services.adms_topology_import.parser import parse_payload  # noqa: E402
from services.adms_topology_import.persistence import (  # noqa: E402
    SESSION_STATUS_MAPPED,
    SESSION_STATUS_PARSED,
    SESSION_STATUS_PUBLISHED,
    SESSION_STATUS_READY_FOR_PUBLISH,
    SESSION_STATUS_RECEIVED,
    SESSION_STATUS_STAGED,
    SESSION_STATUS_VALIDATED,
    AdmsImportPersistenceError,
    InMemoryImportPersistenceRepository,
    derive_session_id,
)
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    TopologyPublishPayload,
    TopologyPublishResult,
)
from services.adms_topology_import.runtime import (  # noqa: E402
    RUNTIME_PIPELINE,
    RuntimeExecutionOptions,
    build_import_coordinator,
    build_runtime_dependencies,
)
from services.adms_topology_import.staging import (  # noqa: E402
    create_staged_import,
    mark_ready_for_publish,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    validate_request,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "persistence-import-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        return TopologyPublishResult(
            version=31,
            version_row={"version": 31, "label": payload.label},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


def _payload() -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "persistence-model-a",
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


def _request(payload: dict | None = None) -> TransportRequest:
    return TransportRequest(
        method="POST",
        scheme="https",
        tls_version="1.2",
        client_certificate_subject="CN=adms-import",
        headers={
            "Authorization": f"Bearer {DEV_BEARER}",
            "Content-Type": "application/json",
            "X-Correlation-ID": CORRELATION_ID,
            "Idempotency-Key": IDEMPOTENCY_KEY,
        },
        body=json.dumps(payload or _payload()),
    )


def _transport():
    return validate_request(_request(), idempotency_store=InMemoryIdempotencyStore())


def _staged():
    parsed = parse_payload(_payload())
    mapped = map_topology(parsed)
    return mark_ready_for_publish(create_staged_import(mapped, staging_id="stage-persist-001"))


def test_import_session_id_is_deterministic():
    transport = _transport()

    assert derive_session_id(transport.idempotency_key, transport.payload_sha256) == (
        derive_session_id(transport.idempotency_key, transport.payload_sha256)
    )


def test_repository_persists_session_staging_history_and_checkpoints():
    repo = InMemoryImportPersistenceRepository()
    transport = _transport()
    parsed = parse_payload(_payload())
    staged = _staged()

    with repo.transaction():
        session = repo.create_import_session(transport, actor="operator")
        session = repo.update_import_session(
            session.session_id,
            status=SESSION_STATUS_PARSED,
            parsed=parsed,
        )
        staging = repo.save_staging(session.session_id, staged)
        history = repo.append_history(
            session.session_id,
            step="stage",
            status=SESSION_STATUS_STAGED,
            reason="topology_staged",
        )
        checkpoint = repo.record_checkpoint(
            session.session_id,
            step="stage",
            data={"staging_id": staged.staging_id},
        )

    assert repo.get_import_session(session.session_id) == session
    assert session.source_system == "adms-supplier-a"
    assert session.external_model_id == "persistence-model-a"
    assert staging.staging_id == "stage-persist-001"
    assert staging.lifecycle == ("staged", "ready_for_publish")
    assert repo.get_staging(session.session_id) == staging
    assert repo.history_for_session(session.session_id) == (history,)
    assert repo.checkpoints_for_session(session.session_id) == (checkpoint,)


def test_transaction_rolls_back_all_persistence_records_on_error():
    repo = InMemoryImportPersistenceRepository()
    transport = _transport()
    session_id = derive_session_id(transport.idempotency_key, transport.payload_sha256)

    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.create_import_session(transport, actor="operator")
            repo.append_history(
                session_id,
                step="transport",
                status=SESSION_STATUS_RECEIVED,
                reason="transport_validated",
            )
            raise RuntimeError("boom")

    assert repo.get_import_session(session_id) is None
    assert repo.history_for_session(session_id) == ()
    assert repo.checkpoints_for_session(session_id) == ()


def test_repository_rejects_duplicate_sessions_deterministically():
    repo = InMemoryImportPersistenceRepository()
    transport = _transport()
    repo.create_import_session(transport, actor="operator")

    with pytest.raises(AdmsImportPersistenceError) as raised:
        repo.create_import_session(transport, actor="operator")

    assert raised.value.reason_code == "duplicate_import_session"
    assert raised.value.location == "session_id"


def test_runtime_persists_execution_history_and_checkpoints_when_injected():
    repo = InMemoryImportPersistenceRepository()
    coordinator = build_import_coordinator(
        build_runtime_dependencies(
            publish_gateway=FakePublishGateway(),
            idempotency_store=InMemoryIdempotencyStore(),
            persistence_repository=repo,
        )
    )

    result = coordinator.submit(
        _request(),
        options=RuntimeExecutionOptions(actor="operator", staging_id="stage-persist-runtime"),
    )
    session_id = derive_session_id(
        result.transport.idempotency_key, result.transport.payload_sha256
    )
    session = repo.get_import_session(session_id)
    staging = repo.get_staging(session_id)
    history = repo.history_for_session(session_id)
    checkpoints = repo.checkpoints_for_session(session_id)

    assert result.steps_completed == RUNTIME_PIPELINE
    assert session is not None
    assert session.status == SESSION_STATUS_PUBLISHED
    assert session.published_version == 31
    assert staging is not None
    assert staging.status == SESSION_STATUS_PUBLISHED
    assert tuple(record.step for record in history) == RUNTIME_PIPELINE
    assert tuple(record.step for record in checkpoints) == RUNTIME_PIPELINE
    assert tuple(record.status for record in history) == (
        SESSION_STATUS_RECEIVED,
        SESSION_STATUS_PARSED,
        SESSION_STATUS_MAPPED,
        SESSION_STATUS_VALIDATED,
        SESSION_STATUS_STAGED,
        SESSION_STATUS_READY_FOR_PUBLISH,
        SESSION_STATUS_PUBLISHED,
    )
