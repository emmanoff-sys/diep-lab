from __future__ import annotations

from reos_exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    REOSException,
    ValidationError,
)

# Thin re-export of the shared exception library (WP-002-05).
# The hierarchy and RFC 7807 handler live in libs/reos-exceptions —
# do not define service-local exception classes for standard error cases.


__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "ExternalServiceError",
    "NotFoundError",
    "REOSException",
    "ValidationError",
]
