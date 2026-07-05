"""FastAPI dependency injection — database session and service factories."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from audit_service.domain.services import AuditService
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends, Request

logger = structlog.get_logger(__name__)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.db_session_factory() as session:
        yield session


async def get_audit_service(
    session: AsyncSession = Depends(get_db),
) -> AuditService:
    return AuditService(session)
