"""WP-006-08 Objective 16 ADMS import production security tests."""

from __future__ import annotations

import json
import os
import sys

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.api import create_runtime_router  # noqa: E402
from services.adms_topology_import.config import Settings  # noqa: E402
from services.adms_topology_import.persistence import (  # noqa: E402
    SESSION_STATUS_RECEIVED,
    InMemoryImportPersistenceRepository,
)
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    TopologyPublishPayload,
    TopologyPublishResult,
)
from services.adms_topology_import.runtime import (  # noqa: E402
    build_import_coordinator,
    build_runtime_dependencies,
)
from services.adms_topology_import.security import (  # noqa: E402
    PERMISSION_ADMIN,
    PERMISSION_CONTROL,
    PERMISSION_READ,
    PERMISSION_SUBMIT,
    AdmsImportSecurityError,
    InMemorySecurityAuditRecorder,
    RuntimeCredentialStore,
    RuntimeSecurityConfig,
    RuntimeSecurityPolicy,
    StaticSecretProvider,
)
from services.adms_topology_import.transport import (  # noqa: E402
    TransportRequest,
    validate_request,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "security-import-001"


class ApiSettings(Settings):
    REQUIRE_TLS = False


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        return TopologyPublishResult(
            version=71,
            version_row={"version": 71, "label": payload.label},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


def _payload(key: str = IDEMPOTENCY_KEY) -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": key,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "security-model-a",
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


def _headers(token: str = DEV_BEARER, key: str = IDEMPOTENCY_KEY, **overrides) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Correlation-ID": CORRELATION_ID,
        "Idempotency-Key": key,
        "X-TLS-Version": "1.2",
        "X-Client-Certificate-Subject": "CN=adms-import",
    }
    headers.update(overrides)
    return headers


def _transport(token: str = DEV_BEARER, **overrides) -> TransportRequest:
    return TransportRequest(
        method="POST",
        scheme=overrides.pop("scheme", "https"),
        tls_version=overrides.pop("tls_version", "1.2"),
        client_certificate_subject=overrides.pop("client_certificate_subject", "CN=adms-import"),
        headers=_headers(token, **overrides),
        body=json.dumps(_payload()),
    )


def _policy(
    *,
    permissions: set[str] | frozenset[str] | None = None,
    require_client_certificate: bool = True,
    audit: InMemorySecurityAuditRecorder | None = None,
) -> tuple[RuntimeSecurityPolicy, InMemorySecurityAuditRecorder]:
    recorder = audit or InMemorySecurityAuditRecorder()
    store = RuntimeCredentialStore(
        secret_provider=StaticSecretProvider({"ADMS_IMPORT_OPERATOR_TOKEN": DEV_BEARER}),
        credential_secrets={"operator": "ADMS_IMPORT_OPERATOR_TOKEN"},
        permissions={"operator": permissions or {PERMISSION_ADMIN}},
        certificate_subjects={"operator": "CN=adms-import"},
    )
    return (
        RuntimeSecurityPolicy(
            credential_store=store,
            config=RuntimeSecurityConfig(
                require_tls=True,
                min_tls_version="1.2",
                require_client_certificate=require_client_certificate,
                require_audit=True,
            ),
            audit_recorder=recorder,
        ),
        recorder,
    )


def _app(policy: RuntimeSecurityPolicy):
    repository = InMemoryImportPersistenceRepository()
    coordinator = build_import_coordinator(
        build_runtime_dependencies(
            settings=ApiSettings,
            publish_gateway=FakePublishGateway(),
            persistence_repository=repository,
        )
    )
    app = FastAPI()
    app.include_router(
        create_runtime_router(
            coordinator=coordinator,
            repository=repository,
            security_policy=policy,
        )
    )
    return app, repository


def _seed_session(repo: InMemoryImportPersistenceRepository) -> str:
    request = TransportRequest(
        method="POST",
        scheme="http",
        headers=_headers(**{"Idempotency-Key": "security-seed-001"}),
        body=json.dumps(_payload("security-seed-001")),
    )
    transport = validate_request(request, settings=ApiSettings)
    session = repo.create_import_session(transport, actor="operator")
    repo.append_history(
        session.session_id,
        step="transport",
        status=SESSION_STATUS_RECEIVED,
        reason="seeded_for_security_test",
    )
    return session.session_id


def test_security_policy_authorises_runtime_request_and_records_audit_event():
    policy, recorder = _policy(permissions={PERMISSION_SUBMIT})

    result = policy.authorize(
        _transport(),
        operation="submit_import",
        required_permission=PERMISSION_SUBMIT,
    )

    assert result.principal.name == "operator"
    assert result.correlation_id == CORRELATION_ID
    assert len(recorder.events) == 1
    assert recorder.events[0].outcome == "success"
    assert recorder.events[0].operation == "submit_import"


def test_security_policy_rejects_invalid_secret_and_records_denial():
    policy, recorder = _policy(permissions={PERMISSION_SUBMIT})

    with pytest.raises(AdmsImportSecurityError) as raised:
        policy.authorize(
            _transport("wrong-token"),
            operation="submit_import",
            required_permission=PERMISSION_SUBMIT,
        )

    assert raised.value.reason_code == "invalid_bearer_token"
    assert recorder.events[-1].outcome == "denied"
    assert recorder.events[-1].reason_code == "invalid_bearer_token"


def test_security_policy_enforces_tls_minimum_and_client_certificate_binding():
    policy, _ = _policy(permissions={PERMISSION_SUBMIT})

    with pytest.raises(AdmsImportSecurityError) as tls_error:
        policy.authorize(
            _transport(scheme="http"),
            operation="submit_import",
            required_permission=PERMISSION_SUBMIT,
        )
    with pytest.raises(AdmsImportSecurityError) as cert_error:
        policy.authorize(
            _transport(client_certificate_subject="CN=unexpected"),
            operation="submit_import",
            required_permission=PERMISSION_SUBMIT,
        )

    assert tls_error.value.reason_code == "https_required"
    assert cert_error.value.reason_code == "client_certificate_mismatch"


def test_security_policy_enforces_operation_permissions():
    policy, _ = _policy(permissions={PERMISSION_READ})

    with pytest.raises(AdmsImportSecurityError) as raised:
        policy.authorize(
            _transport(),
            operation="submit_import",
            required_permission=PERMISSION_SUBMIT,
        )

    assert raised.value.reason_code == "permission_denied"


def test_security_policy_requires_audit_recorder_when_configured():
    store = RuntimeCredentialStore(
        secret_provider=StaticSecretProvider({"ADMS_IMPORT_OPERATOR_TOKEN": DEV_BEARER}),
        credential_secrets={"operator": "ADMS_IMPORT_OPERATOR_TOKEN"},
        permissions={"operator": {PERMISSION_SUBMIT}},
    )
    policy = RuntimeSecurityPolicy(
        credential_store=store,
        config=RuntimeSecurityConfig(require_tls=False, require_audit=True),
    )

    with pytest.raises(AdmsImportSecurityError) as raised:
        policy.authorize(
            _transport(scheme="http"),
            operation="submit_import",
            required_permission=PERMISSION_SUBMIT,
        )

    assert raised.value.reason_code == "audit_recorder_required"


def test_protected_runtime_api_allows_authorised_submit():
    policy, recorder = _policy(permissions={PERMISSION_SUBMIT})
    app, repository = _app(policy)
    client = TestClient(app, base_url="https://testserver")

    response = client.post(
        "/adms/topology-imports",
        json={"payload": _payload(), "actor": "operator"},
        headers=_headers(),
    )

    assert response.status_code == 202, response.text
    assert repository.get_import_session(response.json()["session_id"]) is not None
    assert recorder.events[-1].operation == "submit_import"


def test_protected_runtime_api_denies_unauthorised_control_operation():
    policy, _ = _policy(permissions={PERMISSION_READ})
    app, repository = _app(policy)
    session_id = _seed_session(repository)
    client = TestClient(app, base_url="https://testserver")

    response = client.post(f"/adms/topology-imports/{session_id}/cancel", headers=_headers())

    assert response.status_code == 403
    assert response.json()["detail"]["reason_code"] == "permission_denied"


def test_protected_runtime_api_allows_authorised_read_operation():
    policy, _ = _policy(permissions={PERMISSION_READ})
    app, repository = _app(policy)
    session_id = _seed_session(repository)
    client = TestClient(app, base_url="https://testserver")

    response = client.get(f"/adms/topology-imports/{session_id}", headers=_headers())

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_protected_runtime_api_allows_authorised_retry_operation():
    policy, _ = _policy(permissions={PERMISSION_CONTROL})
    app, repository = _app(policy)
    session_id = _seed_session(repository)
    client = TestClient(app, base_url="https://testserver")

    response = client.post(
        f"/adms/topology-imports/{session_id}/retry",
        json={"reason": "security_authorised"},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "retry_requested"
