"""Role and Permission request/response schemas (WP-005-02)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    id: UUID
    domain: str
    action: str
    slug: str
    description: str | None = None

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Lowercase role name; letters, digits, hyphens, underscores only.",
    )
    description: str | None = None


class RoleUpdate(BaseModel):
    description: str | None = None


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    is_system: bool
    created_at: datetime
    permissions: list[PermissionResponse] = []

    model_config = {"from_attributes": True}


class UserRoleResponse(BaseModel):
    user_id: UUID
    role_id: UUID
    role_name: str
