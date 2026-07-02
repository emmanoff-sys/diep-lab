"""Unit tests for the REOSException hierarchy — WP-002-05 §29.

Each exception class correctly sets its HTTP status, code, message, detail,
and metadata.
"""

from __future__ import annotations

import pytest

from reos_exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    REOSException,
    ValidationError,
)


class TestBaseException:
    def test_attributes(self) -> None:
        exc = REOSException(
            message="Something happened.",
            code="SOMETHING",
            http_status=418,
            detail="More detail.",
            metadata={"k": "v"},
        )
        assert exc.message == "Something happened."
        assert exc.code == "SOMETHING"
        assert exc.http_status == 418
        assert exc.detail == "More detail."
        assert exc.metadata == {"k": "v"}

    def test_detail_defaults_to_message(self) -> None:
        exc = REOSException(message="msg", code="C", http_status=400)
        assert exc.detail == "msg"
        assert exc.metadata == {}

    def test_is_an_exception(self) -> None:
        with pytest.raises(REOSException):
            raise REOSException(message="m", code="C", http_status=500)


@pytest.mark.parametrize(
    ("factory", "expected_status", "expected_code"),
    [
        (lambda: ValidationError("field x is bad"), 422, "VALIDATION_ERROR"),
        (lambda: AuthenticationError(), 401, "AUTHENTICATION_REQUIRED"),
        (lambda: AuthorizationError(), 403, "AUTHORIZATION_DENIED"),
        (lambda: NotFoundError("Customer", 7), 404, "RESOURCE_NOT_FOUND"),
        (lambda: ConflictError("version already published"), 409, "RESOURCE_CONFLICT"),
        (lambda: ExternalServiceError("adms"), 502, "EXTERNAL_SERVICE_ERROR"),
    ],
)
def test_subclass_status_and_code(
    factory: object, expected_status: int, expected_code: str
) -> None:
    exc = factory()  # type: ignore[operator]
    assert isinstance(exc, REOSException)
    assert exc.http_status == expected_status
    assert exc.code == expected_code


class TestSecurityDefaults:
    """WP-002-05 §25 — auth errors must not leak internal detail."""

    def test_authentication_error_message_is_generic(self) -> None:
        exc = AuthenticationError()
        assert exc.detail == "Authentication required."
        assert "password" not in exc.detail.lower()

    def test_authorization_error_message_is_generic(self) -> None:
        exc = AuthorizationError()
        assert exc.detail == "You do not have permission to perform this action."


class TestSubclassDetails:
    def test_not_found_detail_includes_resource_and_id(self) -> None:
        exc = NotFoundError("Meter", "MTR-9")
        assert exc.detail == "Meter with id 'MTR-9' was not found."
        assert exc.message == "Meter was not found."

    def test_validation_error_carries_detail_and_metadata(self) -> None:
        exc = ValidationError("kwp must be positive", metadata={"field": "kwp"})
        assert exc.detail == "kwp must be positive"
        assert exc.metadata == {"field": "kwp"}

    def test_external_service_error_names_service(self) -> None:
        exc = ExternalServiceError("adms", detail="timeout after 30s")
        assert "adms" in exc.message
        assert exc.detail == "timeout after 30s"
