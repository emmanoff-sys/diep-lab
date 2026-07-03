"""Role and Permission management endpoints (WP-005-02 / SRS §RBAC).

All endpoints require at minimum admin:read; mutation endpoints require admin:write.
System roles (is_system=True) are seeded by migration 0001 and are protected:
  - PATCH /roles/{id} → 403 for system roles
  - DELETE /roles/{id} → 403 for system roles
  - POST/DELETE /roles/{id}/permissions → 403 for system roles
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from identity_service.core.rbac import RequirePermission
from identity_service.db.session import get_db
from identity_service.models.role import Permission, Role
from identity_service.schemas.role import (
    PermissionResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)

router = APIRouter(tags=["roles"])

_require_read = RequirePermission("admin:read")
_require_write = RequirePermission("admin:write")

# ---------------------------------------------------------------------------
# Permissions (seeded, read-only via API)
# ---------------------------------------------------------------------------


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_read),
) -> list[PermissionResponse]:
    """List all 21 seeded permissions ordered by domain then action."""
    rows = await db.scalars(
        select(Permission).order_by(Permission.domain, Permission.action)
    )
    return [PermissionResponse.model_validate(p) for p in rows.all()]


@router.get("/permissions/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_read),
) -> PermissionResponse:
    perm = await db.get(Permission, permission_id)
    if not perm:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Permission not found")
    return PermissionResponse.model_validate(perm)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_read),
) -> list[RoleResponse]:
    rows = await db.scalars(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    )
    return [RoleResponse.model_validate(r) for r in rows.all()]


@router.get("/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_read),
) -> RoleResponse:
    role = await db.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    return RoleResponse.model_validate(role)


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_write),
) -> RoleResponse:
    existing = await db.scalar(select(Role).where(Role.name == body.name))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Role name already exists")
    role = Role(name=body.name, description=body.description, is_system=False)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_write),
) -> RoleResponse:
    role = await db.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="System roles cannot be modified")
    if body.description is not None:
        role.description = body.description
    await db.commit()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_write),
) -> None:
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="System roles cannot be deleted")
    await db.delete(role)
    await db.commit()


# ---------------------------------------------------------------------------
# Role–Permission assignment (non-system roles only)
# ---------------------------------------------------------------------------


@router.post(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_permission_to_role(
    role_id: UUID,
    permission_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_write),
) -> None:
    """Assign a permission to a non-system role (idempotent)."""
    role = await db.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Cannot modify system role permissions"
        )
    perm = await db.get(Permission, permission_id)
    if not perm:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Permission not found")
    if perm not in role.permissions:
        role.permissions.append(perm)
        await db.commit()


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_permission_from_role(
    role_id: UUID,
    permission_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(_require_write),
) -> None:
    """Remove a permission from a non-system role (idempotent)."""
    role = await db.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Cannot modify system role permissions"
        )
    perm = await db.get(Permission, permission_id)
    if not perm:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Permission not found")
    if perm in role.permissions:
        role.permissions.remove(perm)
        await db.commit()
