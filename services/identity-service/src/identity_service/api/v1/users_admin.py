"""User role-assignment endpoints (WP-005-02 / SRS §RBAC).

Endpoints:
  GET  /users/{user_id}/roles          — own roles (any auth) or others (admin:read)
  POST /users/{user_id}/roles/{role_id} — assign role (admin:write); records assigned_by
  DELETE /users/{user_id}/roles/{role_id} — remove role (admin:write)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from identity_service.core.rbac import RequirePermission
from identity_service.core.security import get_current_user
from identity_service.db.session import get_db
from identity_service.models.role import Role, user_roles
from identity_service.models.user import User
from identity_service.schemas.role import UserRoleResponse

router = APIRouter(prefix="/users", tags=["users-admin"])

_require_write = RequirePermission("admin:write")


@router.get("/{user_id}/roles", response_model=list[UserRoleResponse])
async def list_user_roles(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserRoleResponse]:
    """Return the roles assigned to a user.

    Any authenticated user may read their own roles.
    admin:read permission is required to read another user's roles.
    """
    if current_user.id != user_id:
        user_perms = {p.slug for r in current_user.roles for p in r.permissions}
        if "admin:read" not in user_perms:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="admin:read required to view other users' roles"
            )
    target = await db.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.roles))
    )
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return [
        UserRoleResponse(user_id=user_id, role_id=r.id, role_name=r.name)
        for r in target.roles
    ]


@router.post("/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role_to_user(
    user_id: UUID,
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_write),
) -> None:
    """Assign a role to a user (idempotent). Records the assigning admin's ID."""
    target = await db.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.roles))
    )
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    if any(r.id == role_id for r in target.roles):
        return  # idempotent — already assigned
    await db.execute(
        user_roles.insert().values(
            user_id=user_id,
            role_id=role_id,
            assigned_by=current_user.id,
        )
    )
    await db.commit()


@router.delete("/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_from_user(
    user_id: UUID,
    role_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(_require_write),
) -> None:
    """Remove a role from a user (idempotent)."""
    if not await db.get(User, user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    if not await db.get(Role, role_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    await db.execute(
        sql_delete(user_roles).where(
            (user_roles.c.user_id == user_id) & (user_roles.c.role_id == role_id)
        )
    )
    await db.commit()
