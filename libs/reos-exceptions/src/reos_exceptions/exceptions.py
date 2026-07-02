"""REOSException hierarchy — LLD v2.0 §2.2 (extracted as specified).

Six concrete subclasses map to their documented HTTP status codes:
ValidationError 422, AuthenticationError 401, AuthorizationError 403,
NotFoundError 404, ConflictError 409, ExternalServiceError 502.

Not covered here: 429 (rate limiter) and 503 (load balancer) — raised by
infrastructure, not application code. See README "Not Covered by This
Library" (WP-002-05 §9, §35).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "ExternalServiceError",
    "NotFoundError",
    "REOSException",
    "ValidationError",
]


class REOSException(Exception):  # noqa: N818 — name mandated by LLD v2.0 §2.2 (frozen baseline)
    """Base class for every DAEP / RE-OS application exception.

    :param message: human-readable summary (becomes RFC 7807 ``title``).
    :param code: stable machine-readable error code (e.g. ``RESOURCE_NOT_FOUND``).
    :param http_status: HTTP status the global handler responds with.
    :param detail: occurrence-specific explanation (RFC 7807 ``detail``).
    :param metadata: extra RFC 7807 extension members merged into the response.
    """

    def __init__(
        self,
        message: str,
        code: str,
        http_status: int,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.detail = detail if detail is not None else message
        self.metadata = metadata if metadata is not None else {}


class ValidationError(REOSException):
    """Request payload failed domain validation — HTTP 422."""

    def __init__(
        self,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message="Request validation failed.",
            code="VALIDATION_ERROR",
            http_status=422,
            detail=detail,
            metadata=metadata,
        )


class AuthenticationError(REOSException):
    """Caller identity could not be established — HTTP 401.

    Security (WP-002-05 §25): default message stays generic — never leak
    which part of the credential check failed.
    """

    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            message="Authentication required.",
            code="AUTHENTICATION_REQUIRED",
            http_status=401,
            metadata=metadata,
        )


class AuthorizationError(REOSException):
    """Caller lacks permission for this action — HTTP 403.

    Security (WP-002-05 §25): default message stays generic — never reveal
    the required permission or internal role structure.
    """

    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            message="You do not have permission to perform this action.",
            code="AUTHORIZATION_DENIED",
            http_status=403,
            metadata=metadata,
        )


class NotFoundError(REOSException):
    """Requested resource does not exist (or is soft-deleted) — HTTP 404."""

    def __init__(
        self,
        resource: str,
        resource_id: str | int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=f"{resource} was not found.",
            code="RESOURCE_NOT_FOUND",
            http_status=404,
            detail=f"{resource} with id '{resource_id}' was not found.",
            metadata=metadata,
        )


class ConflictError(REOSException):
    """Request conflicts with current resource state — HTTP 409."""

    def __init__(
        self,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message="The request conflicts with the current state of the resource.",
            code="RESOURCE_CONFLICT",
            http_status=409,
            detail=detail,
            metadata=metadata,
        )


class ExternalServiceError(REOSException):
    """Upstream/external dependency failed — HTTP 502."""

    def __init__(
        self,
        service: str,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=f"External service '{service}' is unavailable.",
            code="EXTERNAL_SERVICE_ERROR",
            http_status=502,
            detail=detail,
            metadata=metadata,
        )
