"""Integration tests: Kafka consumer (ENG-SPEC-005-04 §26.2 / §10).

These tests use the _parse_message + write_event pipeline with real DB.
Full end-to-end Kafka requires a running broker; those tests are marked
with @pytest.mark.kafka and skipped unless AUDIT_INTEGRATION_KAFKA=1.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from audit_service.core.kafka import _parse_message
from audit_service.domain.services import AuditService


@pytest.mark.asyncio
async def test_iam_audit_event_persisted_via_parse(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    msg = {
        "event_id": str(uuid4()),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": str(uuid4()),
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": str(uuid4()),
        "service_name": "identity-service",
        "timestamp_utc": "2026-07-04T10:00:00+00:00",
    }
    event_data = _parse_message("iam.audit.events", msg)
    event = await svc.write_event(event_data, source="kafka")
    assert event.event_type == "auth.login.success"
    assert event.event_hash


@pytest.mark.asyncio
async def test_user_registered_converted_and_persisted(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    msg = {
        "event_type": "user.registered",
        "user_id": str(uuid4()),
        "email": "user@example.com",
        "timestamp": "2026-07-04T10:00:00+00:00",
        "correlation_id": str(uuid4()),
    }
    event_data = _parse_message("user.registered", msg)
    event = await svc.write_event(event_data, source="kafka")
    assert event.event_type == "user.registered"
    assert event.action == "user.register"


@pytest.mark.asyncio
async def test_duplicate_event_id_idempotent_skip(db_session: object) -> None:
    from audit_service.core.exceptions import AuditEventDuplicate
    svc = AuditService(db_session)  # type: ignore[arg-type]
    msg = {
        "event_id": str(uuid4()),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": str(uuid4()),
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": str(uuid4()),
        "service_name": "identity-service",
        "timestamp_utc": "2026-07-04T10:00:00+00:00",
    }
    event_data = _parse_message("iam.audit.events", msg)
    await svc.write_event(event_data, source="kafka")

    # Second write with same event_id should raise AuditEventDuplicate (consumer handles it)
    with pytest.raises(AuditEventDuplicate):
        await svc.write_event(event_data, source="kafka")


@pytest.mark.asyncio
async def test_schema_invalid_message_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        _parse_message("iam.audit.events", {"event_id": str(uuid4())})
