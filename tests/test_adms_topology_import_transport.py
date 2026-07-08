"""WP-006-07 Objective 3 transport and authentication tests."""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.config import Settings  # noqa: E402
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    TransportValidationError,
    validate_request,
)

BODY = b'{"contract_version":"1.0"}'
DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"


def _request(**overrides):
    headers = {
        "Authorization": f"Bearer {DEV_BEARER}",
        "Content-Type": "application/json",
        "X-Correlation-ID": CORRELATION_ID,
        "Idempotency-Key": "import-001",
    }
    headers.update(overrides.pop("headers", {}))
    values = {
        "method": "POST",
        "scheme": "https",
        "tls_version": "1.2",
        "client_certificate_subject": "CN=adms-import",
        "headers": headers,
        "body": BODY,
    }
    values.update(overrides)
    return TransportRequest(**values)


def _reason_for(request):
    try:
        validate_request(request)
    except TransportValidationError as exc:
        return exc.reason_code
    return None


def test_valid_request_returns_transport_context():
    result = validate_request(_request())

    assert result.principal.name == "adms-import-service"
    assert result.principal.auth_scheme == "bearer"
    assert result.principal.client_certificate_subject == "CN=adms-import"
    assert result.correlation_id == CORRELATION_ID
    assert result.idempotency_key == "import-001"
    assert result.payload_sha256 == hashlib.sha256(BODY).hexdigest()
    assert result.body == BODY
    assert result.replay is False
    assert result.diagnostics == ()


def test_header_names_are_case_insensitive():
    request = _request(
        headers={
            "authorization": f"Bearer {DEV_BEARER}",
            "content-type": "application/json; charset=utf-8",
            "x-correlation-id": CORRELATION_ID,
            "idempotency-key": "import-001",
        }
    )

    assert validate_request(request).idempotency_key == "import-001"


def test_rejects_non_post_method():
    assert _reason_for(_request(method="GET")) == "unsupported_method"


def test_rejects_non_https_transport():
    assert _reason_for(_request(scheme="http")) == "https_required"


def test_rejects_unsupported_tls_version():
    assert _reason_for(_request(tls_version="1.1")) == "unsupported_tls_version"


def test_tls_requirement_can_be_disabled_for_isolated_tests():
    class LocalSettings(Settings):
        REQUIRE_TLS = False

    request = _request(scheme="http", tls_version=None)

    assert validate_request(request, settings=LocalSettings).principal.name == "adms-import-service"


def test_rejects_missing_bearer_token():
    request = _request(headers={"Authorization": ""})

    assert _reason_for(request) == "missing_bearer_token"


def test_rejects_invalid_bearer_token():
    request = _request(headers={"Authorization": "Bearer wrong-token"})

    assert _reason_for(request) == "invalid_bearer_token"


def test_custom_auth_token_mapping_is_supported():
    class CustomSettings(Settings):
        AUTH_TOKENS_RAW = "custom-token=custom-principal"

    request = _request(headers={"Authorization": "Bearer custom-token"})

    assert validate_request(request, settings=CustomSettings).principal.name == "custom-principal"


def test_rejects_unsupported_content_type():
    request = _request(headers={"Content-Type": "text/plain"})

    assert _reason_for(request) == "unsupported_content_type"


def test_rejects_missing_correlation_id():
    request = _request(headers={"X-Correlation-ID": ""})

    assert _reason_for(request) == "invalid_correlation_id"


def test_rejects_malformed_correlation_id():
    request = _request(headers={"X-Correlation-ID": "not-a-uuid"})

    assert _reason_for(request) == "invalid_correlation_id"


def test_rejects_invalid_idempotency_key():
    request = _request(headers={"Idempotency-Key": "short"})

    assert _reason_for(request) == "invalid_idempotency_key"


def test_rejects_empty_body():
    assert _reason_for(_request(body=b"")) == "empty_body"


def test_text_body_is_encoded_for_payload_hashing():
    request = _request(body='{"contract_version":"1.0"}')

    result = validate_request(request)

    assert result.body == BODY
    assert result.payload_sha256 == hashlib.sha256(BODY).hexdigest()


def test_idempotency_store_marks_exact_replay():
    store = InMemoryIdempotencyStore()
    first = validate_request(_request(), idempotency_store=store)
    second = validate_request(_request(), idempotency_store=store)

    assert first.replay is False
    assert second.replay is True


def test_idempotency_store_rejects_conflicting_reuse():
    store = InMemoryIdempotencyStore()
    validate_request(_request(), idempotency_store=store)

    with pytest.raises(TransportValidationError) as raised:
        validate_request(
            _request(body=b'{"contract_version":"1.0","changed":true}'), idempotency_store=store
        )

    assert raised.value.category == "idempotency"
    assert raised.value.reason_code == "idempotency_key_conflict"
    assert raised.value.offending_object == "import-001"
    assert raised.value.location == "headers.Idempotency-Key"


def test_error_contains_deterministic_transport_diagnostic():
    with pytest.raises(TransportValidationError) as raised:
        validate_request(_request(method="PUT"))

    error = raised.value
    assert error.category == "transport"
    assert error.reason_code == "unsupported_method"
    assert error.description == "ADMS topology import transport accepts POST only"
    assert error.offending_object == "PUT"
    assert error.location == "method"
