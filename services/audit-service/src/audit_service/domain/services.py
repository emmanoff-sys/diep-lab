"""AuditService — business logic layer (ENG-SPEC-005-04 §7.2).

Responsibilities:
- Orchestrate write: fetch prev_hash → compute event_hash → repo.write_event
- Orchestrate query: validate filters → repo.query_events → emit meta-audit
- Orchestrate verify-chain: fetch events → walk chain → emit meta-audit
- Immutability: no update/delete methods exist; DB trigger is the final guard
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from audit_service.config import settings
from audit_service.core.exceptions import (
    AuditChainNotFoundError,
    AuditEventDuplicateError,
    AuditEventNotFoundError,
    AuditInvalidPartitionTypeError,
    AuditQueryDateRangeTooLargeError,
    AuditQueryInvalidDateRangeError,
    AuditQueryInvalidDatetimeError,
)
from audit_service.core.hash_chain import compute_event_hash, verify_single_link
from audit_service.domain.events import make_meta_event
from audit_service.domain.models import AuditEvent
from audit_service.domain.repositories import AuditEventRepository
from prometheus_client import Counter, Histogram
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_VALID_PARTITION_TYPES = frozenset(["actor", "date"])

_events_written = Counter(
    "audit_events_written_total", "Audit events written", ["source", "outcome"]
)
_write_duration = Histogram(
    "audit_events_write_duration_seconds",
    "Write latency",
    ["source"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
_events_queried = Counter("audit_events_queried_total", "Query API calls")
_query_duration = Histogram(
    "audit_events_query_duration_seconds",
    "Query latency",
    buckets=[0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)
_chain_broken = Counter(
    "audit_chain_broken_total", "Chain integrity violations detected", ["partition_type"]
)


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditEventRepository(session)
        self._session = session

    async def write_event(self, event_data: dict[str, Any], source: str = "rest") -> AuditEvent:
        """Compute hash chain link and persist the event.

        Raises AuditEventDuplicateError if event_id already exists.
        """
        start = time.monotonic()
        actor_id: UUID = event_data["actor_id"]  # type: ignore[assignment]

        prev_hash = await self._repo.get_last_event_hash(actor_id)
        event_hash = compute_event_hash(
            event_id=event_data["event_id"],  # type: ignore[arg-type]
            event_type=str(event_data["event_type"]),
            actor_id=actor_id,
            action=str(event_data["action"]),
            outcome=str(event_data["outcome"]),
            timestamp_utc=event_data["timestamp_utc"],  # type: ignore[arg-type]
            prev_event_hash=prev_hash,
        )

        try:
            event = await self._repo.write_event(event_data, prev_hash, event_hash)
            await self._session.commit()
        except sa_exc.IntegrityError as exc:
            await self._session.rollback()
            if "uq_audit_events_event_id" in str(exc):
                _events_written.labels(source=source, outcome="duplicate").inc()
                raise AuditEventDuplicateError(event_data["event_id"]) from exc  # type: ignore[arg-type]
            _events_written.labels(source=source, outcome="failure").inc()
            raise

        elapsed = time.monotonic() - start
        _write_duration.labels(source=source).observe(elapsed)
        _events_written.labels(source=source, outcome="success").inc()
        logger.debug(
            "audit.event_written",
            event_type=event_data["event_type"],
            outcome=event_data["outcome"],
            source=source,
            duration_ms=round(elapsed * 1000, 2),
        )
        return event

    async def get_event(self, event_id: UUID) -> AuditEvent:
        event = await self._repo.get_event_by_id(event_id)
        if event is None:
            raise AuditEventNotFoundError(event_id)
        return event

    async def query_events(
        self,
        requesting_actor_id: UUID,
        requesting_actor_type: str,
        correlation_id: UUID,
        actor_id: UUID | None = None,
        event_type: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        outcome: str | None = None,
        service_name: str | None = None,
        filter_correlation_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
        sort: str = "desc",
    ) -> dict[str, Any]:
        """Query events with filter validation and meta-audit emission."""
        start = time.monotonic()

        date_from, date_to = self._resolve_date_range(date_from, date_to)
        page_size = min(page_size, settings.QUERY_MAX_PAGE_SIZE)

        events, total = await self._repo.query_events(
            actor_id=actor_id,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            service_name=service_name,
            correlation_id=filter_correlation_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
            sort=sort,
        )

        elapsed = time.monotonic() - start
        _query_duration.observe(elapsed)
        _events_queried.inc()

        # Meta-audit: fire-and-forget (AUD-FR-004)
        meta = make_meta_event(
            event_type="audit.log.queried",
            action="audit.query",
            actor_id=requesting_actor_id,
            actor_type=requesting_actor_type,
            correlation_id=correlation_id,
            metadata={"result_count": total, "page": page, "page_size": page_size},
        )
        asyncio.create_task(self._write_meta(meta))

        total_pages = math.ceil(total / page_size) if page_size else 1
        return {
            "events": events,
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def verify_chain(
        self,
        partition_type: str,
        partition_key: str,
        requesting_actor_id: UUID,
        requesting_actor_type: str,
        correlation_id: UUID,
    ) -> dict[str, Any]:
        """Walk the hash chain for a partition; return verification result."""
        if partition_type not in _VALID_PARTITION_TYPES:
            raise AuditInvalidPartitionTypeError(partition_type)

        start = time.monotonic()
        events = await self._repo.get_events_for_chain_verify(partition_type, partition_key)
        if not events:
            raise AuditChainNotFoundError(partition_type, partition_key)

        chain_valid = True
        broken_at_event_id: UUID | None = None
        broken_at_position: int | None = None

        for position, event in enumerate(events):
            ok = verify_single_link(
                event_id=event.event_id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                action=event.action,
                outcome=event.outcome,
                timestamp_utc=event.timestamp_utc,
                prev_event_hash=event.prev_event_hash,
                stored_hash=event.event_hash,
            )
            if not ok:
                chain_valid = False
                broken_at_event_id = event.event_id
                broken_at_position = position
                _chain_broken.labels(partition_type=partition_type).inc()
                logger.critical(
                    "audit.chain_integrity_broken",
                    partition_type=partition_type,
                    partition_key=partition_key,
                    broken_at_position=position,
                    event_id=str(event.event_id),
                )
                break

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)

        # Meta-audit: fire-and-forget (AUD-FR-016)
        meta = make_meta_event(
            event_type="audit.chain.verified",
            action="audit.verify_chain",
            actor_id=requesting_actor_id,
            actor_type=requesting_actor_type,
            correlation_id=correlation_id,
            metadata={
                "partition_type": partition_type,
                "partition_key": partition_key,
                "chain_valid": chain_valid,
                "events_checked": len(events),
            },
        )
        asyncio.create_task(self._write_meta(meta))

        return {
            "partition_type": partition_type,
            "partition_key": partition_key,
            "chain_valid": chain_valid,
            "events_checked": len(events),
            "broken_at_event_id": broken_at_event_id,
            "broken_at_position": broken_at_position,
            "verification_duration_ms": elapsed_ms,
        }

    def _resolve_date_range(
        self, date_from: datetime | None, date_to: datetime | None
    ) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        if date_from is not None and date_from.tzinfo is None:
            raise AuditQueryInvalidDatetimeError("date_from must be UTC-aware")
        if date_to is not None and date_to.tzinfo is None:
            raise AuditQueryInvalidDatetimeError("date_to must be UTC-aware")

        resolved_from = date_from or (now - timedelta(days=settings.QUERY_DEFAULT_DATE_RANGE_DAYS))
        resolved_to = date_to or now

        if resolved_to < resolved_from:
            raise AuditQueryInvalidDateRangeError("date_to must be >= date_from")

        delta_days = (resolved_to - resolved_from).days
        if delta_days > settings.QUERY_MAX_DATE_RANGE_DAYS:
            raise AuditQueryDateRangeTooLargeError(
                f"Date range {delta_days} days exceeds maximum {settings.QUERY_MAX_DATE_RANGE_DAYS}"
            )

        return resolved_from, resolved_to

    async def _write_meta(self, meta: dict[str, Any]) -> None:
        """Write a meta-audit event; errors are logged and suppressed."""
        try:
            await self.write_event(meta, source="internal")
        except Exception:
            logger.warning("audit.meta_event_write_failed", event_type=meta.get("event_type"))
