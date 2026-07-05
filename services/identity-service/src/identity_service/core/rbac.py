"""RBAC enforcement FastAPI dependencies (WP-005-02 / SRS §RBAC).

Usage:
    # Require ALL listed permissions (AND semantics):
    _guard = RequirePermission("admin:read", "admin:write")
    @router.post("/foo", dependencies=[Depends(_guard)])

    # Require at least ONE listed role (OR semantics):
    _guard = RequireRole("admin", "superadmin")
    @router.get("/bar")
    async def bar(user: User = Depends(_guard)): ...

System roles (is_system=True) are immutable via the management API but are
fully functional for permission enforcement here.
"""

from __future__ import annotations

from identity_service.core.security import get_current_user
from identity_service.models.user import User

from fastapi import Depends, HTTPException, status


class RequirePermission:
    """Assert the current user holds ALL of the specified permissions (AND)."""

    def __init__(self, *required: str) -> None:
        self._required: frozenset[str] = frozenset(required)

    async def __call__(self, user: User = Depends(get_current_user)) -> User:
        user_perms = {p.slug for role in user.roles for p in role.permissions}
        if not self._required.issubset(user_perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user


class RequireRole:
    """Assert the current user holds at least ONE of the specified roles (OR)."""

    def __init__(self, *required: str) -> None:
        self._required: frozenset[str] = frozenset(required)

    async def __call__(self, user: User = Depends(get_current_user)) -> User:
        user_roles = {r.name for r in user.roles}
        if not self._required.intersection(user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return user
