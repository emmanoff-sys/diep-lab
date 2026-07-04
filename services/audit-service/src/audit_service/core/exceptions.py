"""Domain exceptions for the audit service (ENG-SPEC-005-04 §11.6)."""

from __future__ import annotations

from uuid import UUID


class AuditServiceError(Exception):
    """Base exception for all audit-service domain errors."""


class AuditEventDuplicate(AuditServiceError):
    """Raised when an event_id already exists in the store."""

    def __init__(self, event_id: UUID) -> None:
        self.event_id = event_id
        super().__init__(f"Audit event {event_id} already exists")


class AuditEventNotFound(AuditServiceError):
    """Raised when a requested event_id is not in the store."""

    def __init__(self, event_id: UUID) -> None:
        self.event_id = event_id
        super().__init__(f"Audit event {event_id} not found")


class AuditChainNotFound(AuditServiceError):
    """Raised when the requested partition has no events."""

    def __init__(self, partition_type: str, partition_key: str) -> None:
        self.partition_type = partition_type
        self.partition_key = partition_key
        super().__init__(f"No events for partition {partition_type}/{partition_key}")


class AuditInvalidPartitionType(AuditServiceError):
    """Raised when partition_type is not 'actor' or 'date'."""

    def __init__(self, partition_type: str) -> None:
        self.partition_type = partition_type
        super().__init__(f"Invalid partition_type '{partition_type}'; must be 'actor' or 'date'")


class AuditQueryInvalidDateRange(AuditServiceError):
    """Raised when date_to < date_from."""


class AuditQueryDateRangeTooLarge(AuditServiceError):
    """Raised when the query date range exceeds QUERY_MAX_DATE_RANGE_DAYS."""


class AuditQueryInvalidDatetime(AuditServiceError):
    """Raised when a naive (timezone-unaware) datetime is submitted in a query."""


class AuditWriteUnauthorized(AuditServiceError):
    """Raised when the JWT audience is not reos-internal on the write endpoint."""


class AuditReadUnauthorized(AuditServiceError):
    """Raised when the caller lacks admin:audit permission."""


class TokenValidationError(AuditServiceError):
    """Raised when JWT validation fails (expired, wrong alg, bad sig, wrong aud)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Token validation failed: {reason}")


class JWKSFetchError(AuditServiceError):
    """Raised when the JWKS endpoint cannot be reached or returns a bad response."""
