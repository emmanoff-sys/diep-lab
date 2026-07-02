from __future__ import annotations

# PLACEHOLDER: Local exception hierarchy for this scaffold.
# Replace ServiceBaseException with the shared base from libs/exceptions/
# once WP-002-05 delivers the shared library — do not ship this stub to production.

__all__ = ["ServiceBaseException", "NotFoundError", "ValidationError", "AuthorisationError"]


class ServiceBaseException(Exception):
    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class NotFoundError(ServiceBaseException):
    def __init__(self, resource: str, resource_id: int | str) -> None:
        super().__init__(
            message=f"{resource} id={resource_id} was not found.",
            error_code="RESOURCE_NOT_FOUND",
        )


class ValidationError(ServiceBaseException):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, error_code="VALIDATION_ERROR")


class AuthorisationError(ServiceBaseException):
    def __init__(self) -> None:
        super().__init__(
            message="You do not have permission to perform this action.",
            error_code="FORBIDDEN",
        )
