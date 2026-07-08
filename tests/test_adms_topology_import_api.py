"""WP-006-08 Objective 13 ADMS import runtime API tests."""

from __future__ import annotations

import json
import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.api import create_runtime_router  # noqa: E402
from services.adms_topology_import.config import Settings  # noqa: E402
from services.adms_topology_import.persistence import (  # noqa: E402
    SESSION_STATUS_CANCELLED,
    SESSION_STATUS_RECEIVED,
    SESSION_STATUS_RETRY_REQUESTED,
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
    build_import_coordinator,
    build_runtime_dependencies,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    validate_request,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "api-import-001"


class ApiSettings(Settings):
    REQUIRE_TLS = False


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        return TopologyPublishResult(
            version=41,
            version_row={"version": 41, "label": payload.label},
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
            "model_id": "api-model-a",
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


def _headers(**overrides) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {DEV_BEARER}",
        "Content-Type": "application/json",
        "X-Correlation-ID": CORRELATION_ID,
        "Idempotency-Key": IDEMPOTENCY_KEY,
    }
    headers.update(overrides)
    return headers


def _app(repo: InMemoryImportPersistenceRepository | None = None):
    repository = repo or InMemoryImportPersistenceRepository()
    coordinator = build_import_coordinator(
        build_runtime_dependencies(
            settings=ApiSettings,
            publish_gateway=FakePublishGateway(),
            idempotency_store=InMemoryIdempotencyStore(),
            persistence_repository=repository,
        )
    )
    app = FastAPI()
    app.include_router(create_runtime_router(coordinator=coordinator, repository=repository))
    return app, repository


def _seed_session(repo: InMemoryImportPersistenceRepository, key: str = "api-seed-001") -> str:
    request = TransportRequest(
        method="POST",
        scheme="http",
        headers=_headers(**{"Idempotency-Key": key}),
        body=json.dumps(_payload()),
    )
    transport = validate_request(request, settings=ApiSettings)
    session = repo.create_import_session(transport, actor="operator")
    repo.append_history(
        session.session_id,
        step="transport",
        status=SESSION_STATUS_RECEIVED,
        reason="seeded_for_api_test",
    )
    return session.session_id


def test_submit_import_executes_runtime_and_returns_session_status():
    app, repository = _app()
    client = TestClient(app)

    response = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator", "staging_id": "stage-api-001"},
        headers=_headers(),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "published"
    assert body["published_version"] == 41
    assert body["staging_id"] == "stage-api-001"
    assert body["steps_completed"] == list(RUNTIME_PIPELINE)
    assert repository.get_import_session(body["session_id"]) is not None


def test_get_import_status_returns_persisted_session_evidence():
    app, _ = _app()
    client = TestClient(app)
    submit = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator"},
        headers=_headers(),
    )
    session_id = submit.json()["session_id"]

    response = client.get(f"/adms/topology-imports/{session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "published"
    assert body["external_model_id"] == "api-model-a"
    assert body["published_version"] == 41


def test_get_import_history_returns_history_and_checkpoints():
    app, _ = _app()
    client = TestClient(app)
    submit = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator"},
        headers=_headers(),
    )
    session_id = submit.json()["session_id"]

    response = client.get(f"/adms/topology-imports/{session_id}/history")

    assert response.status_code == 200
    body = response.json()
    assert [item["step"] for item in body["history"]] == list(RUNTIME_PIPELINE)
    assert [item["step"] for item in body["checkpoints"]] == list(RUNTIME_PIPELINE)


def test_cancel_import_marks_non_terminal_session_cancelled():
    repo = InMemoryImportPersistenceRepository()
    session_id = _seed_session(repo)
    app, _ = _app(repo)
    client = TestClient(app)

    response = client.post(f"/adms/topology-imports/{session_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == SESSION_STATUS_CANCELLED
    history = repo.history_for_session(session_id)
    assert history[-1].step == "cancel"
    assert history[-1].status == SESSION_STATUS_CANCELLED


def test_retry_import_records_retry_request_for_non_terminal_session():
    repo = InMemoryImportPersistenceRepository()
    session_id = _seed_session(repo, key="api-retry-001")
    app, _ = _app(repo)
    client = TestClient(app)

    response = client.post(
        f"/adms/topology-imports/{session_id}/retry", json={"reason": "operator"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == SESSION_STATUS_RETRY_REQUESTED
    history = repo.history_for_session(session_id)
    assert history[-1].step == "retry"
    assert history[-1].reason == "operator"


def test_terminal_import_cannot_be_cancelled_or_retried():
    app, _ = _app()
    client = TestClient(app)
    submit = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator"},
        headers=_headers(),
    )
    session_id = submit.json()["session_id"]

    cancel = client.post(f"/adms/topology-imports/{session_id}/cancel")
    retry = client.post(f"/adms/topology-imports/{session_id}/retry", json={"reason": "operator"})

    assert cancel.status_code == 409
    assert cancel.json()["detail"]["reason_code"] == "import_already_terminal"
    assert retry.status_code == 409
    assert retry.json()["detail"]["reason_code"] == "import_already_terminal"


def test_submit_import_translates_transport_errors_deterministically():
    app, _ = _app()
    client = TestClient(app)

    response = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator"},
        headers=_headers(Authorization="Bearer wrong-token"),
    )

    assert response.status_code == 401
    assert response.json()["detail"]["reason_code"] == "invalid_bearer_token"


def test_unknown_session_returns_deterministic_not_found():
    app, _ = _app()
    client = TestClient(app)

    response = client.get("/adms/topology-imports/import-missing")

    assert response.status_code == 404
    assert response.json()["detail"]["reason_code"] == "unknown_import_session"


def test_health_endpoint_returns_runtime_api_status():
    app, _ = _app()
    client = TestClient(app)

    response = client.get("/adms/topology-imports/-/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "adms-topology-import",
        "ready": True,
        "metrics_enabled": True,
        "detail": "runtime_api_ready",
    }


def test_session_id_matches_persistence_derivation():
    app, _ = _app()
    client = TestClient(app)

    response = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator"},
        headers=_headers(),
    )
    request = TransportRequest(
        method="POST",
        scheme="http",
        headers=_headers(),
        body=json.dumps(_payload()),
    )
    transport = validate_request(request, settings=ApiSettings)

    assert response.json()["session_id"] == derive_session_id(
        transport.idempotency_key,
        transport.payload_sha256,
    )
