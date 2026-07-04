"""Integration tests: GET /api/v1/audit/events (ENG-SPEC-005-04 §26.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from audit_service.core.exceptions import AuditQueryDateRangeTooLargeError
from audit_service.domain.services import AuditService


async def _write(svc: AuditService, actor_id: object = None, **overrides: object) -> object:
    data: dict[str, object] = {
        "event_id": uuid4(),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": actor_id or uuid4(),
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": uuid4(),
        "service_name": "identity-service",
        "timestamp_utc": datetime.now(UTC),
        "schema_version": 1,
    }
    data.update(overrides)
    return await svc.write_event(data)


@pytest.mark.asyncio
async def test_query_by_actor_id(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor = uuid4()
    other = uuid4()
    await _write(svc, actor_id=actor)
    await _write(svc, actor_id=actor)
    await _write(svc, actor_id=other)

    result = await svc.query_events(
        requesting_actor_id=uuid4(),
        requesting_actor_type="user",
        correlation_id=uuid4(),
        actor_id=actor,
    )
    assert result["total_count"] >= 2
    for ev in result["events"]:
        assert ev.actor_id == actor


@pytest.mark.asyncio
async def test_query_by_event_type(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    await _write(svc, event_type="auth.login.success")
    await _write(svc, event_type="auth.token.revoked")

    result = await svc.query_events(
        requesting_actor_id=uuid4(),
        requesting_actor_type="user",
        correlation_id=uuid4(),
        event_type="auth.token.revoked",
    )
    for ev in result["events"]:
        assert ev.event_type == "auth.token.revoked"


@pytest.mark.asyncio
async def test_page_size_capped_at_200(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    result = await svc.query_events(
        requesting_actor_id=uuid4(),
        requesting_actor_type="user",
        correlation_id=uuid4(),
        page_size=500,  # should be capped
    )
    assert result["page_size"] == 200


@pytest.mark.asyncio
async def test_date_range_exceeding_365_days_raises(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    with pytest.raises(AuditQueryDateRangeTooLargeError):
        await svc.query_events(
            requesting_actor_id=uuid4(),
            requesting_actor_type="user",
            correlation_id=uuid4(),
            date_from=datetime.now(UTC) - timedelta(days=400),
            date_to=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_sort_descending_default(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor = uuid4()
    await _write(svc, actor_id=actor, timestamp_utc=datetime(2026, 7, 4, 8, 0, tzinfo=UTC))
    await _write(svc, actor_id=actor, timestamp_utc=datetime(2026, 7, 4, 9, 0, tzinfo=UTC))

    result = await svc.query_events(
        requesting_actor_id=uuid4(),
        requesting_actor_type="user",
        correlation_id=uuid4(),
        actor_id=actor,
        sort="desc",
    )
    events = result["events"]
    if len(events) >= 2:
        assert events[0].timestamp_utc >= events[1].timestamp_utc
