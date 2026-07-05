"""AuditEventRepository — DB write and query; no update/delete methods.

All SQL uses SQLAlchemy parameterised queries (AUD-SEC-010).
No raw string interpolation in this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import structlog
from audit_service.domain.models import AuditEvent, ChainState
from sqlalchemy import desc, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_PARTITION_TYPE_ACTOR = "actor"


class AuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_event(
        self, event_data: dict[str, object], prev_event_hash: str | None, event_hash: str
    ) -> AuditEvent:
        """INSERT audit event + UPSERT chain_state in one transaction.

        Returns the inserted AuditEvent. Raises IntegrityError on duplicate event_id
        (caller translates to AuditEventDuplicateError).
        """
        now = datetime.now(UTC)
        event = AuditEvent(
            id=uuid4(),
            event_id=event_data["event_id"],
            event_type=str(event_data["event_type"]),
            actor_type=str(event_data["actor_type"]),
            actor_id=event_data["actor_id"],
            actor_username=event_data.get("actor_username"),
            actor_ip_address=event_data.get("actor_ip_address"),
            actor_user_agent=event_data.get("actor_user_agent"),
            action=str(event_data["action"]),
            resource_type=str(event_data["resource_type"]),
            resource_id=event_data.get("resource_id"),
            outcome=str(event_data["outcome"]),
            outcome_reason=event_data.get("outcome_reason"),
            correlation_id=event_data["correlation_id"],
            session_id=event_data.get("session_id"),
            service_name=str(event_data["service_name"]),
            service_version=event_data.get("service_version"),
            prev_event_hash=prev_event_hash,
            event_hash=event_hash,
            event_metadata=(
                event_data.get("metadata") if isinstance(event_data.get("metadata"), dict) else None
            ),
            timestamp_utc=event_data["timestamp_utc"],
            ingested_at_utc=now,
            schema_version=int(cast(str | int, event_data.get("schema_version", 1))),
        )
        self._session.add(event)

        actor_id_str = str(event_data["actor_id"])
        timestamp = event_data["timestamp_utc"]

        upsert_stmt = (
            pg_insert(ChainState)
            .values(
                partition_type=_PARTITION_TYPE_ACTOR,
                partition_key=actor_id_str,
                last_event_id=event_data["event_id"],
                last_event_hash=event_hash,
                event_count=1,
                first_event_at=timestamp,
                last_event_at=timestamp,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["partition_type", "partition_key"],
                set_={
                    "last_event_id": event_data["event_id"],
                    "last_event_hash": event_hash,
                    "event_count": ChainState.event_count + 1,
                    "last_event_at": timestamp,
                    "updated_at": now,
                },
            )
        )
        await self._session.execute(upsert_stmt)
        return event

    async def get_event_by_id(self, event_id: UUID) -> AuditEvent | None:
        stmt = select(AuditEvent).where(AuditEvent.event_id == event_id)
        return cast(AuditEvent | None, await self._session.scalar(stmt))

    async def get_last_event_hash(self, actor_id: UUID) -> str | None:
        """Return the most recent event_hash for the given actor partition."""
        stmt = (
            select(AuditEvent.event_hash)
            .where(AuditEvent.actor_id == actor_id)
            .order_by(desc(AuditEvent.timestamp_utc))
            .limit(1)
        )
        return cast(str | None, await self._session.scalar(stmt))

    async def query_events(  # noqa: C901 — complexity is inherent to the multi-filter query domain
        self,
        actor_id: UUID | None = None,
        event_type: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: str | None = None,
        service_name: str | None = None,
        correlation_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
        sort: str = "desc",
    ) -> tuple[list[AuditEvent], int]:
        """Return (events, total_count) for the given filters."""
        stmt = select(AuditEvent)
        count_stmt = select(func.count()).select_from(AuditEvent)

        if actor_id is not None:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
            count_stmt = count_stmt.where(AuditEvent.actor_id == actor_id)
        if event_type is not None:
            stmt = stmt.where(AuditEvent.event_type == event_type)
            count_stmt = count_stmt.where(AuditEvent.event_type == event_type)
        if action is not None:
            stmt = stmt.where(AuditEvent.action == action)
            count_stmt = count_stmt.where(AuditEvent.action == action)
        if resource_type is not None:
            stmt = stmt.where(AuditEvent.resource_type == resource_type)
            count_stmt = count_stmt.where(AuditEvent.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(AuditEvent.resource_id == resource_id)
            count_stmt = count_stmt.where(AuditEvent.resource_id == resource_id)
        if outcome is not None:
            stmt = stmt.where(AuditEvent.outcome == outcome)
            count_stmt = count_stmt.where(AuditEvent.outcome == outcome)
        if service_name is not None:
            stmt = stmt.where(AuditEvent.service_name == service_name)
            count_stmt = count_stmt.where(AuditEvent.service_name == service_name)
        if correlation_id is not None:
            stmt = stmt.where(AuditEvent.correlation_id == correlation_id)
            count_stmt = count_stmt.where(AuditEvent.correlation_id == correlation_id)
        if date_from is not None:
            stmt = stmt.where(AuditEvent.timestamp_utc >= date_from)
            count_stmt = count_stmt.where(AuditEvent.timestamp_utc >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditEvent.timestamp_utc <= date_to)
            count_stmt = count_stmt.where(AuditEvent.timestamp_utc <= date_to)

        order = desc(AuditEvent.timestamp_utc) if sort == "desc" else AuditEvent.timestamp_utc
        stmt = stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)

        total: int = (await self._session.scalar(count_stmt)) or 0
        result = await self._session.execute(stmt)
        events = list(result.scalars().all())
        return events, total

    async def get_events_for_chain_verify(
        self, partition_type: str, partition_key: str
    ) -> list[AuditEvent]:
        """Return all events for a partition ordered ascending for chain verification."""
        if partition_type == _PARTITION_TYPE_ACTOR:
            actor_id = UUID(partition_key)
            stmt = (
                select(AuditEvent)
                .where(AuditEvent.actor_id == actor_id)
                .order_by(AuditEvent.timestamp_utc)
            )
        else:
            # date partition: YYYY-MM-DD
            stmt = (
                select(AuditEvent)
                .where(
                    text("DATE(timestamp_utc AT TIME ZONE 'UTC') = :date_val").bindparams(
                        date_val=partition_key
                    )
                )
                .order_by(AuditEvent.timestamp_utc)
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_chain_state(self, partition_type: str, partition_key: str) -> ChainState | None:
        stmt = select(ChainState).where(
            ChainState.partition_type == partition_type,
            ChainState.partition_key == partition_key,
        )
        return cast(ChainState | None, await self._session.scalar(stmt))
