"""SQLAlchemy 2.x mapped classes for audit schema (ENG-SPEC-005-04 §8, §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import SMALLINT, BigInteger, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_audit_events_event_id"),
        Index("ix_audit_events_actor_id", "actor_id", "timestamp_utc"),
        Index("ix_audit_events_event_type", "event_type", "timestamp_utc"),
        Index("ix_audit_events_resource", "resource_type", "resource_id", "timestamp_utc"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
        Index("ix_audit_events_outcome", "outcome", "timestamp_utc"),
        Index("ix_audit_events_service_name", "service_name", "timestamp_utc"),
        {"schema": "audit"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), primary_key=True, nullable=False
    )
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    actor_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    actor_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    service_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_event_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    ingested_at_utc: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(SMALLINT, nullable=False, default=1)


class ChainState(Base):
    __tablename__ = "chain_state"
    __table_args__ = {"schema": "audit"}

    partition_type: Mapped[str] = mapped_column(Text, primary_key=True)
    partition_key: Mapped[str] = mapped_column(Text, primary_key=True)
    last_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    last_event_hash: Mapped[str] = mapped_column(Text, nullable=False)
    event_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    first_event_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
