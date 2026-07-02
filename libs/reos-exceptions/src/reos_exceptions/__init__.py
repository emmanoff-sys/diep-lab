"""reos-exceptions — DAEP / RE-OS shared exception hierarchy and RFC 7807 handler.

Authority: WP-002-05 | LLD v2.0 §2.2 (Error Handling Standard — direct,
literal source) | DRDP v1.0 §21.3 (frontend contract this output satisfies).

Usage::

    from reos_exceptions import NotFoundError, register_exception_handlers

    register_exception_handlers(app)             # once, in create_app()
    raise NotFoundError("Customer", customer_id) # anywhere in the service
"""

from reos_exceptions.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    REOSException,
    ValidationError,
)
from reos_exceptions.handlers import register_exception_handlers

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "ExternalServiceError",
    "NotFoundError",
    "REOSException",
    "ValidationError",
    "register_exception_handlers",
]
