"""JWT Bearer token validation — get_current_user FastAPI dependency (WP-005-02).

Usage in protected endpoints:
    current_user: User = Depends(get_current_user)

All exceptions raised here are HTTP 401 with WWW-Authenticate: Bearer so clients
know to re-authenticate. Permission/role enforcement is in core.rbac.
"""

from __future__ import annotations

from uuid import UUID

from identity_service.core.jwt import jwt_manager
from identity_service.db.session import get_db
from identity_service.models.role import Role
from identity_service.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=True)

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the RS256 Bearer token and return the fully-loaded User.

    Roles and permissions are selectin-loaded so downstream RBAC checks
    don't trigger additional DB round-trips.
    """
    try:
        payload = jwt_manager.decode_access_token(credentials.credentials)
    except (ValueError, RuntimeError):
        raise _401 from None

    try:
        user_id = UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        raise _401 from None

    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
