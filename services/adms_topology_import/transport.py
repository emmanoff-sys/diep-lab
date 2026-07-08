"""Authentication and transport validation for ADMS topology import.

Objective 3 remains a pure boundary layer. It validates request metadata,
authentication, TLS posture, correlation identifiers, idempotency keys, and
payload hashes. It does not parse topology payloads, map objects, persist
state, stage imports, publish versions, or communicate with an ADMS runtime.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Protocol

from .config import Settings
from .parser import ParserDiagnostic

ERROR_CATEGORY_TRANSPORT = "transport"
ERROR_CATEGORY_AUTHENTICATION = "authentication"
ERROR_CATEGORY_IDEMPOTENCY = "idempotency"

HEADER_AUTHORIZATION = "authorization"
HEADER_CONTENT_TYPE = "content-type"
HEADER_CORRELATION_ID = "x-correlation-id"
HEADER_IDEMPOTENCY_KEY = "idempotency-key"
SUPPORTED_CONTENT_TYPE = "application/json"
SUPPORTED_TLS_VERSIONS = ("1.2", "1.3")
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


@dataclass(frozen=True)
class TransportPrincipal:
    name: str
    auth_scheme: str
    client_certificate_subject: str | None = None


@dataclass(frozen=True)
class TransportRequest:
    method: str
    scheme: str
    headers: Mapping[str, str]
    body: bytes | str
    tls_version: str | None = None
    client_certificate_subject: str | None = None


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    payload_sha256: str
    correlation_id: str


@dataclass(frozen=True)
class TransportValidationResult:
    principal: TransportPrincipal
    correlation_id: str
    idempotency_key: str
    payload_sha256: str
    body: bytes
    replay: bool
    diagnostics: tuple[ParserDiagnostic, ...] = ()


class IdempotencyStore(Protocol):
    def reserve(self, key: str, payload_sha256: str, correlation_id: str) -> bool:
        """Reserve an idempotency key.

        Return ``True`` for a first observation and ``False`` for an exact
        replay. Raise ``TransportValidationError`` for key reuse with a
        different payload or correlation id.
        """


class InMemoryIdempotencyStore:
    """Process-local idempotency store for tests and dependency injection."""

    def __init__(self) -> None:
        self._records: MutableMapping[str, IdempotencyRecord] = {}

    def reserve(self, key: str, payload_sha256: str, correlation_id: str) -> bool:
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = IdempotencyRecord(key, payload_sha256, correlation_id)
            return True
        if existing.payload_sha256 == payload_sha256 and existing.correlation_id == correlation_id:
            return False
        _raise(
            ERROR_CATEGORY_IDEMPOTENCY,
            "idempotency_key_conflict",
            "Idempotency key was reused with different request content",
            offending_object=key,
            location="headers.Idempotency-Key",
        )


class TransportValidationError(ValueError):
    """Deterministic transport/authentication validation error."""

    def __init__(
        self,
        *,
        category: str,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{category}:{reason_code}: {description}")
        self.diagnostic = ParserDiagnostic(
            category=category,
            reason_code=reason_code,
            description=description,
            offending_object=offending_object,
            location=location,
        )

    @property
    def category(self) -> str:
        return self.diagnostic.category

    @property
    def reason_code(self) -> str:
        return self.diagnostic.reason_code

    @property
    def description(self) -> str:
        return self.diagnostic.description

    @property
    def offending_object(self) -> str | None:
        return self.diagnostic.offending_object

    @property
    def location(self) -> str | None:
        return self.diagnostic.location


def validate_request(
    request: TransportRequest,
    *,
    settings: type[Settings] = Settings,
    idempotency_store: IdempotencyStore | None = None,
) -> TransportValidationResult:
    """Validate an inbound ADMS import transport request."""

    headers = _normalise_headers(request.headers)
    _validate_method(request.method)
    _validate_secure_transport(request, settings=settings)
    _validate_content_type(headers)
    principal = _authenticate(headers, request, settings=settings)
    body = _normalise_body(request.body)
    correlation_id = _correlation_id(headers)
    idempotency_key = _idempotency_key(headers)
    payload_sha256 = hashlib.sha256(body).hexdigest()
    first_seen = True
    if idempotency_store is not None:
        first_seen = idempotency_store.reserve(idempotency_key, payload_sha256, correlation_id)

    return TransportValidationResult(
        principal=principal,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        payload_sha256=payload_sha256,
        body=body,
        replay=not first_seen,
    )


def _normalise_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value).strip() for key, value in headers.items()}


def _validate_method(method: str) -> None:
    if method.upper() != "POST":
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "unsupported_method",
            "ADMS topology import transport accepts POST only",
            offending_object=method,
            location="method",
        )


def _validate_secure_transport(request: TransportRequest, *, settings: type[Settings]) -> None:
    if not settings.REQUIRE_TLS:
        return
    if request.scheme.lower() != "https":
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "https_required",
            "ADMS topology import requires HTTPS transport",
            offending_object=request.scheme,
            location="scheme",
        )
    if request.tls_version not in SUPPORTED_TLS_VERSIONS:
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "unsupported_tls_version",
            f"ADMS topology import requires TLS {settings.MIN_TLS_VERSION} or newer",
            offending_object=request.tls_version or "missing",
            location="tls_version",
        )


def _validate_content_type(headers: Mapping[str, str]) -> None:
    content_type = headers.get(HEADER_CONTENT_TYPE, "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != SUPPORTED_CONTENT_TYPE:
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "unsupported_content_type",
            "ADMS topology import requires application/json content",
            offending_object=content_type or "missing",
            location="headers.Content-Type",
        )


def _authenticate(
    headers: Mapping[str, str],
    request: TransportRequest,
    *,
    settings: type[Settings],
) -> TransportPrincipal:
    auth = headers.get(HEADER_AUTHORIZATION, "")
    if not auth.startswith("Bearer "):
        _raise(
            ERROR_CATEGORY_AUTHENTICATION,
            "missing_bearer_token",
            "Missing or malformed Bearer token",
            offending_object="Authorization",
            location="headers.Authorization",
        )
    token = auth[len("Bearer ") :].strip()
    principal_name = settings.auth_tokens().get(token)
    if principal_name is None:
        _raise(
            ERROR_CATEGORY_AUTHENTICATION,
            "invalid_bearer_token",
            "Bearer token is not authorised for ADMS topology import",
            offending_object="Bearer",
            location="headers.Authorization",
        )
    return TransportPrincipal(
        name=principal_name,
        auth_scheme="bearer",
        client_certificate_subject=request.client_certificate_subject,
    )


def _normalise_body(body: bytes | str) -> bytes:
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not isinstance(body, bytes) or not body:
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "empty_body",
            "ADMS topology import request body must be non-empty bytes or text",
            offending_object=type(body).__name__,
            location="body",
        )
    return body


def _correlation_id(headers: Mapping[str, str]) -> str:
    value = headers.get(HEADER_CORRELATION_ID, "")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "invalid_correlation_id",
            "X-Correlation-ID must be a valid UUID",
            offending_object=value or "missing",
            location="headers.X-Correlation-ID",
        )


def _idempotency_key(headers: Mapping[str, str]) -> str:
    value = headers.get(HEADER_IDEMPOTENCY_KEY, "")
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        _raise(
            ERROR_CATEGORY_TRANSPORT,
            "invalid_idempotency_key",
            "Idempotency-Key must be 8-128 characters of letters, digits, "
            "dot, underscore, colon, or hyphen",
            offending_object=value or "missing",
            location="headers.Idempotency-Key",
        )
    return value


def _raise(
    category: str,
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise TransportValidationError(
        category=category,
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
