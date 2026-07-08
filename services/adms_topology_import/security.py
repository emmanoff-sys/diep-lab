"""Production security controls for ADMS topology import runtime.

WP-006-08 Objective 16 adds runtime credential management, secure secret
injection, runtime authentication and authorisation enforcement, TLS
configuration validation, and audit logging enforcement for security-sensitive
runtime API operations. It integrates with the existing runtime API and
transport metadata without redesigning orchestration, persistence, worker, or
scheduler responsibilities.
"""

from __future__ import annotations

import hmac
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .parser import ParserDiagnostic
from .transport import (
    HEADER_AUTHORIZATION,
    HEADER_CORRELATION_ID,
    TransportPrincipal,
    TransportRequest,
)

ERROR_CATEGORY_SECURITY = "security"

PERMISSION_ADMIN = "admin"
PERMISSION_SUBMIT = "submit_import"
PERMISSION_READ = "read_import"
PERMISSION_CONTROL = "control_import"

SUPPORTED_TLS_VERSIONS = ("1.2", "1.3")


@dataclass(frozen=True)
class RuntimeCredential:
    principal: str
    secret: str
    permissions: frozenset[str]
    client_certificate_subject: str | None = None


@dataclass(frozen=True)
class RuntimeSecurityConfig:
    require_tls: bool = True
    min_tls_version: str = "1.2"
    require_client_certificate: bool = False
    require_audit: bool = True


@dataclass(frozen=True)
class SecurityAuditEvent:
    event_type: str
    operation: str
    principal: str | None
    outcome: str
    correlation_id: str | None
    reason_code: str | None
    occurred_at: str


@dataclass(frozen=True)
class SecurityValidationResult:
    principal: TransportPrincipal
    operation: str
    correlation_id: str | None


class SecretProvider(Protocol):
    def get_secret(self, name: str) -> str | None:
        """Return a secret value by name without exposing unrelated secrets."""


class SecurityAuditRecorder(Protocol):
    def record(self, event: SecurityAuditEvent) -> None:
        """Record a security audit event."""


class EnvironmentSecretProvider:
    """Environment-backed secret provider for runtime credential injection."""

    def get_secret(self, name: str) -> str | None:
        return os.getenv(name)


class StaticSecretProvider:
    """Deterministic secret provider for tests and dependency injection."""

    def __init__(self, secrets: Mapping[str, str]) -> None:
        self._secrets = dict(secrets)

    def get_secret(self, name: str) -> str | None:
        return self._secrets.get(name)


class InMemorySecurityAuditRecorder:
    """In-memory audit recorder for tests and dependency injection."""

    def __init__(self) -> None:
        self._events: list[SecurityAuditEvent] = []

    @property
    def events(self) -> tuple[SecurityAuditEvent, ...]:
        return tuple(self._events)

    def record(self, event: SecurityAuditEvent) -> None:
        self._events.append(event)


class RuntimeCredentialStore:
    """Credential store that resolves secrets through an injected provider."""

    def __init__(
        self,
        *,
        secret_provider: SecretProvider,
        credential_secrets: Mapping[str, str],
        permissions: Mapping[str, set[str] | frozenset[str]],
        certificate_subjects: Mapping[str, str] | None = None,
    ) -> None:
        self._secret_provider = secret_provider
        self._credential_secrets = dict(credential_secrets)
        self._permissions = {
            principal: frozenset(values) for principal, values in permissions.items()
        }
        self._certificate_subjects = dict(certificate_subjects or {})

    def credentials(self) -> tuple[RuntimeCredential, ...]:
        resolved: list[RuntimeCredential] = []
        for principal, secret_name in self._credential_secrets.items():
            secret = self._secret_provider.get_secret(secret_name)
            if not secret:
                continue
            permissions = self._permissions.get(principal, frozenset())
            if not permissions:
                continue
            resolved.append(
                RuntimeCredential(
                    principal=principal,
                    secret=secret,
                    permissions=permissions,
                    client_certificate_subject=self._certificate_subjects.get(principal),
                )
            )
        return tuple(resolved)


class RuntimeSecurityPolicy:
    """Security policy for protected runtime API operations."""

    def __init__(
        self,
        *,
        credential_store: RuntimeCredentialStore,
        config: RuntimeSecurityConfig | None = None,
        audit_recorder: SecurityAuditRecorder | None = None,
    ) -> None:
        self._credential_store = credential_store
        self._config = config or RuntimeSecurityConfig()
        self._audit_recorder = audit_recorder

    @property
    def config(self) -> RuntimeSecurityConfig:
        return self._config

    def authorize(
        self,
        request: TransportRequest,
        *,
        operation: str,
        required_permission: str,
    ) -> SecurityValidationResult:
        """Authenticate and authorise a runtime API request."""

        principal: TransportPrincipal | None = None
        correlation_id = _correlation_id(request.headers)
        try:
            _validate_tls(request, config=self._config)
            credential = _authenticate(request, self._credential_store.credentials())
            _validate_client_certificate(request, credential, config=self._config)
            _authorise(credential, required_permission)
            principal = TransportPrincipal(
                name=credential.principal,
                auth_scheme="bearer",
                client_certificate_subject=request.client_certificate_subject,
            )
            self._audit(
                operation=operation,
                principal=principal.name,
                outcome="success",
                correlation_id=correlation_id,
                reason_code=None,
            )
            return SecurityValidationResult(
                principal=principal,
                operation=operation,
                correlation_id=correlation_id,
            )
        except AdmsImportSecurityError as exc:
            self._audit(
                operation=operation,
                principal=principal.name if principal else None,
                outcome="denied",
                correlation_id=correlation_id,
                reason_code=exc.reason_code,
            )
            raise

    def _audit(
        self,
        *,
        operation: str,
        principal: str | None,
        outcome: str,
        correlation_id: str | None,
        reason_code: str | None,
    ) -> None:
        if self._audit_recorder is None:
            if self._config.require_audit:
                _raise(
                    "audit_recorder_required",
                    "Security-sensitive runtime operations require audit logging",
                    location="security.audit_recorder",
                )
            return
        event = SecurityAuditEvent(
            event_type="adms.topology_import.security",
            operation=operation,
            principal=principal,
            outcome=outcome,
            correlation_id=correlation_id,
            reason_code=reason_code,
            occurred_at=datetime.now(UTC).isoformat(),
        )
        try:
            self._audit_recorder.record(event)
        except Exception as exc:  # noqa: BLE001 - security boundary converts sink failures
            _raise(
                "security_audit_failed",
                "Security audit event could not be recorded",
                offending_object=type(exc).__name__,
                location="security.audit_recorder",
            )


class AdmsImportSecurityError(ValueError):
    """Deterministic production security error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_SECURITY}:{reason_code}: {description}")
        self.diagnostic = ParserDiagnostic(
            category=ERROR_CATEGORY_SECURITY,
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


def _validate_tls(request: TransportRequest, *, config: RuntimeSecurityConfig) -> None:
    if not config.require_tls:
        return
    if request.scheme.lower() != "https":
        _raise(
            "https_required",
            "Runtime security requires HTTPS transport",
            offending_object=request.scheme,
            location="scheme",
        )
    if request.tls_version not in SUPPORTED_TLS_VERSIONS:
        _raise(
            "unsupported_tls_version",
            f"Runtime security requires TLS {config.min_tls_version} or newer",
            offending_object=request.tls_version or "missing",
            location="tls_version",
        )
    if _tls_rank(request.tls_version) < _tls_rank(config.min_tls_version):
        _raise(
            "tls_version_below_minimum",
            f"Runtime security requires TLS {config.min_tls_version} or newer",
            offending_object=request.tls_version,
            location="tls_version",
        )


def _authenticate(
    request: TransportRequest,
    credentials: tuple[RuntimeCredential, ...],
) -> RuntimeCredential:
    headers = _normalise_headers(request.headers)
    auth = headers.get(HEADER_AUTHORIZATION, "")
    if not auth.startswith("Bearer "):
        _raise(
            "missing_bearer_token",
            "Missing or malformed Bearer token",
            offending_object="Authorization",
            location="headers.Authorization",
        )
    token = auth[len("Bearer ") :].strip()
    for credential in credentials:
        if hmac.compare_digest(token, credential.secret):
            return credential
    _raise(
        "invalid_bearer_token",
        "Bearer token is not authorised for ADMS topology import runtime",
        offending_object="Bearer",
        location="headers.Authorization",
    )


def _validate_client_certificate(
    request: TransportRequest,
    credential: RuntimeCredential,
    *,
    config: RuntimeSecurityConfig,
) -> None:
    if not config.require_client_certificate and credential.client_certificate_subject is None:
        return
    expected = credential.client_certificate_subject
    actual = request.client_certificate_subject
    if not actual:
        _raise(
            "client_certificate_required",
            "Runtime security requires a client certificate subject",
            offending_object=credential.principal,
            location="client_certificate_subject",
        )
    if expected is not None and actual != expected:
        _raise(
            "client_certificate_mismatch",
            "Client certificate subject does not match credential binding",
            offending_object=actual,
            location="client_certificate_subject",
        )


def _authorise(credential: RuntimeCredential, required_permission: str) -> None:
    if PERMISSION_ADMIN in credential.permissions:
        return
    if required_permission in credential.permissions:
        return
    _raise(
        "permission_denied",
        "Principal is not authorised for this ADMS topology import operation",
        offending_object=credential.principal,
        location="principal.permissions",
    )


def _correlation_id(headers: Mapping[str, str]) -> str | None:
    value = _normalise_headers(headers).get(HEADER_CORRELATION_ID)
    if value is None:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        _raise(
            "invalid_correlation_id",
            "X-Correlation-ID must be a valid UUID when provided",
            offending_object=value,
            location="headers.X-Correlation-ID",
        )


def _normalise_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value).strip() for key, value in headers.items()}


def _tls_rank(version: str | None) -> int:
    if version is None:
        return -1
    try:
        major, minor = version.split(".", 1)
        return (int(major) * 100) + int(minor)
    except ValueError:
        return -1


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportSecurityError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
