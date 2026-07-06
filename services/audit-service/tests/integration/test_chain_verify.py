"""Integration tests: GET /api/v1/audit/verify-chain (ENG-SPEC-005-04 §26.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from audit_service.core.exceptions import AuditChainNotFoundError
from audit_service.domain.services import AuditService
from sqlalchemy import text


async def _write_chain(svc: AuditService, actor_id: object, count: int = 3) -> list[object]:
    events = []
    for i in range(count):
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
            "timestamp_utc": datetime(2026, 7, 4, 10, i, 0, tzinfo=UTC),
            "schema_version": 1,
        }
        events.append(await svc.write_event(data))
    return events


@pytest.mark.asyncio(loop_scope="session")
async def test_valid_chain_returns_chain_valid_true(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor_id = uuid4()
    await _write_chain(svc, actor_id, count=3)

    result = await svc.verify_chain(
        partition_type="actor",
        partition_key=str(actor_id),
        requesting_actor_id=uuid4(),
        requesting_actor_type="user",
        correlation_id=uuid4(),
    )
    assert result["chain_valid"] is True
    assert result["events_checked"] == 3
    assert result["broken_at_event_id"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_empty_partition_raises_not_found(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    with pytest.raises(AuditChainNotFoundError):
        await svc.verify_chain(
            partition_type="actor",
            partition_key=str(uuid4()),
            requesting_actor_id=uuid4(),
            requesting_actor_type="user",
            correlation_id=uuid4(),
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_tampered_hash_detected(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor_id = uuid4()
    events = await _write_chain(svc, actor_id, count=2)

    # Tamper: directly update event_hash via raw SQL with a test-only trigger bypass.
    event_id = events[0].event_id  # type: ignore[union-attr]
    try:
        await db_session.execute(  # type: ignore[union-attr]
            text("ALTER TABLE audit.audit_events DISABLE TRIGGER tg_audit_events_immutable")
        )
        await db_session.execute(  # type: ignore[union-attr]
            text(
                "UPDATE audit.audit_events SET event_hash = 'tampered_hash_value' "
                "WHERE event_id = :eid"
            ).bindparams(eid=event_id)
        )
        await db_session.commit()  # type: ignore[union-attr]
    finally:
        await db_session.execute(  # type: ignore[union-attr]
            text("ALTER TABLE audit.audit_events ENABLE TRIGGER tg_audit_events_immutable")
        )
        await db_session.commit()  # type: ignore[union-attr]
    db_session.expire_all()  # type: ignore[union-attr]

    result = await svc.verify_chain(
        partition_type="actor",
        partition_key=str(actor_id),
        requesting_actor_id=uuid4(),
        requesting_actor_type="user",
        correlation_id=uuid4(),
    )
    assert result["chain_valid"] is False
    assert result["broken_at_event_id"] is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_verify_chain_generates_meta_event(db_session: object) -> None:
    svc = AuditService(db_session)  # type: ignore[arg-type]
    actor_id = uuid4()
    await _write_chain(svc, actor_id, count=1)

    meta_written: list[str] = []
    original_write_meta = svc._write_meta

    async def _capture_meta(meta: object) -> None:
        meta_written.append(meta["event_type"])  # type: ignore[index]
        await original_write_meta(meta)  # type: ignore[arg-type]

    svc._write_meta = _capture_meta  # type: ignore[method-assign]

    import asyncio
    from unittest.mock import patch

    with patch("asyncio.create_task", side_effect=lambda coro: asyncio.ensure_future(coro)):
        await svc.verify_chain(
            partition_type="actor",
            partition_key=str(actor_id),
            requesting_actor_id=uuid4(),
            requesting_actor_type="user",
            correlation_id=uuid4(),
        )
        await asyncio.sleep(0.1)  # let task complete

    assert "audit.chain.verified" in meta_written
