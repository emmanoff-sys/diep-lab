"""Integration tests: PostgreSQL immutability trigger (ENG-SPEC-005-04 §26.2 / AUD-SEC-001).

AUD-FR-005 — UPDATE and DELETE on audit.audit_events MUST raise an exception.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from audit_service.domain.services import AuditService
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError


@pytest.mark.asyncio
async def test_update_raises_exception(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor_id = uuid4()
    data = {
        "event_id": uuid4(),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": actor_id,
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": uuid4(),
        "service_name": "identity-service",
        "timestamp_utc": datetime.now(UTC),
        "schema_version": 1,
    }
    event = await svc.write_event(data)

    with pytest.raises((ProgrammingError, Exception), match="append-only"):
        await db_session.execute(  # type: ignore[union-attr]
            text(
                "UPDATE audit.audit_events SET outcome = 'failure' " "WHERE event_id = :eid"
            ).bindparams(eid=str(event.event_id))
        )
        await db_session.commit()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_delete_raises_exception(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor_id = uuid4()
    data = {
        "event_id": uuid4(),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": actor_id,
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": uuid4(),
        "service_name": "identity-service",
        "timestamp_utc": datetime.now(UTC),
        "schema_version": 1,
    }
    event = await svc.write_event(data)

    with pytest.raises((ProgrammingError, Exception), match="append-only"):
        await db_session.execute(  # type: ignore[union-attr]
            text("DELETE FROM audit.audit_events WHERE event_id = :eid").bindparams(
                eid=str(event.event_id)
            )
        )
        await db_session.commit()  # type: ignore[union-attr]
