"""Query parameter schema for GET /api/v1/audit/events (ENG-SPEC-005-04 §11.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AuditEventQuery(BaseModel):
    actor_id: UUID | None = None
    event_type: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    outcome: Literal["success", "failure", "denied"] | None = None
    service_name: str | None = None
    correlation_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort: Literal["asc", "desc"] = "desc"
