"""Audit event factory helpers — build AuditEventCreate dicts for internal emission.

Used by:
- Meta-audit: audit.log.queried (GET /audit/events)
- Meta-audit: audit.chain.verified (GET /verify-chain)
- user.registered Kafka consumer (converts existing message format)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4


def make_meta_event(
    event_type: str,
    action: str,
    actor_id: UUID,
    actor_type: str,
    correlation_id: UUID,
    resource_type: str = "audit_log",
    resource_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a minimal AuditEventCreate dict for internal meta-events."""
    return {
        "event_id": uuid4(),
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": "success",
        "correlation_id": correlation_id,
        "service_name": "audit-service",
        "service_version": None,
        "metadata": metadata,
        "timestamp_utc": datetime.now(UTC),
        "schema_version": 1,
    }


def user_registered_to_audit(kafka_msg: dict[str, object]) -> dict[str, object]:
    """Convert a user.registered Kafka message to AuditEventCreate dict.

    user.registered schema (from identity-service):
        {event_type, user_id, email, timestamp, correlation_id}
    """
    user_id_raw = kafka_msg.get("user_id", "")
    correlation_id_raw = kafka_msg.get("correlation_id", str(uuid4()))
    timestamp_raw = kafka_msg.get("timestamp")

    if isinstance(timestamp_raw, str):
        ts = datetime.fromisoformat(timestamp_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
    else:
        ts = datetime.now(UTC)

    return {
        "event_id": uuid4(),
        "event_type": "user.registered",
        "actor_type": "user",
        "actor_id": UUID(str(user_id_raw)),
        "action": "user.register",
        "resource_type": "user",
        "resource_id": str(user_id_raw),
        "outcome": "success",
        "correlation_id": UUID(str(correlation_id_raw)),
        "service_name": "identity-service",
        "service_version": None,
        "metadata": None,
        "timestamp_utc": ts,
        "schema_version": 1,
    }
