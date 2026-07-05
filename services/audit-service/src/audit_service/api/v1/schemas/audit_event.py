"""Request/response schemas for the audit service API (ENG-SPEC-005-04 §11.5)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditEventCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: UUID
    event_type: str = Field(max_length=100)
    actor_type: Literal["user", "service", "system"]
    actor_id: UUID
    actor_username: str | None = Field(default=None, max_length=100)
    actor_ip_address: str | None = Field(default=None, max_length=45)
    actor_user_agent: str | None = Field(default=None, max_length=512)
    action: str = Field(max_length=100)
    resource_type: str = Field(max_length=100)
    resource_id: str | None = Field(default=None, max_length=255)
    outcome: Literal["success", "failure", "denied"]
    outcome_reason: str | None = Field(default=None, max_length=500)
    correlation_id: UUID
    session_id: str | None = Field(default=None, max_length=255)
    service_name: str = Field(max_length=100)
    service_version: str | None = Field(default=None, max_length=50)
    metadata: dict[str, Any] | None = None
    timestamp_utc: datetime
    schema_version: int = 1

    @field_validator("timestamp_utc")
    @classmethod
    def must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp_utc must be UTC-aware (naive datetimes rejected)")
        return v

    @field_validator("metadata")
    @classmethod
    def metadata_size_limit(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(json.dumps(v)) > 4096:
            raise ValueError("metadata serialised size exceeds 4096 bytes")
        return v


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    event_type: str
    actor_type: str
    actor_id: UUID
    actor_username: str | None
    actor_ip_address: str | None
    actor_user_agent: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    outcome_reason: str | None
    correlation_id: UUID
    session_id: str | None
    service_name: str
    service_version: str | None
    prev_event_hash: str | None
    event_hash: str
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="event_metadata")
    timestamp_utc: datetime
    ingested_at_utc: datetime
    schema_version: int


class AuditEventListResponse(BaseModel):
    events: list[AuditEventResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class ChainVerifyResponse(BaseModel):
    partition_type: str
    partition_key: str
    chain_valid: bool
    events_checked: int
    broken_at_event_id: UUID | None
    broken_at_position: int | None
    verification_duration_ms: float


class ErrorResponse(BaseModel):
    error_code: str
    detail: str
    correlation_id: str | None = None
