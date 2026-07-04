"""Integration tests: POST /api/v1/audit/events (ENG-SPEC-005-04 §26.2).

Real DB; no mocking of DB layer (STANDARDS.md §7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from audit_service.core.exceptions import AuditEventDuplicate
from audit_service.domain.services import AuditService


@pytest.mark.asyncio
async def test_write_event_persisted(db_session: object, base_event_data: dict) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    event = await svc.write_event(base_event_data)
    assert event.event_id == base_event_data["event_id"]
    assert event.event_hash  # non-empty hash computed
    assert event.ingested_at_utc is not None


@pytest.mark.asyncio
async def test_write_event_hash_chain_populated(db_session: object, base_event_data: dict) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    event = await svc.write_event(base_event_data)
    # First event: prev_event_hash is NULL, hash computed with GENESIS sentinel
    assert event.prev_event_hash is None
    assert len(event.event_hash) == 64  # SHA-256 hex digest


@pytest.mark.asyncio
async def test_duplicate_event_id_raises(db_session: object, base_event_data: dict) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    await svc.write_event(base_event_data)

    # New session to avoid session-level cache
    with pytest.raises(AuditEventDuplicate):
        await svc.write_event(base_event_data)


@pytest.mark.asyncio
async def test_second_event_links_to_first(db_session: object) -> None:
    actor_id = uuid4()
    svc = AuditService(db_session)  # type: ignore[arg-type]

    ev1 = {
        "event_id": uuid4(), "event_type": "auth.login.success", "actor_type": "user",
        "actor_id": actor_id, "action": "login", "resource_type": "session",
        "outcome": "success", "correlation_id": uuid4(), "service_name": "identity-service",
        "timestamp_utc": datetime(2026, 7, 4, 10, 0, 0, tzinfo=UTC), "schema_version": 1,
    }
    ev2 = {
        "event_id": uuid4(), "event_type": "auth.token.refreshed", "actor_type": "user",
        "actor_id": actor_id, "action": "token.refresh", "resource_type": "session",
        "outcome": "success", "correlation_id": uuid4(), "service_name": "identity-service",
        "timestamp_utc": datetime(2026, 7, 4, 10, 1, 0, tzinfo=UTC), "schema_version": 1,
    }

    first = await svc.write_event(ev1)
    second = await svc.write_event(ev2)

    assert second.prev_event_hash == first.event_hash


@pytest.mark.asyncio
async def test_chain_state_upserted(db_session: object, base_event_data: dict) -> None:
    from audit_service.domain.repositories import AuditEventRepository
    svc = AuditService(db_session)  # type: ignore[arg-type]
    event = await svc.write_event(base_event_data)

    repo = AuditEventRepository(db_session)  # type: ignore[arg-type]
    chain = await repo.get_chain_state("actor", str(base_event_data["actor_id"]))
    assert chain is not None
    assert chain.last_event_id == event.event_id
    assert chain.event_count == 1
