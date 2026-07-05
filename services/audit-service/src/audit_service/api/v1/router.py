"""API v1 router — assembles all endpoint routers under /api/v1."""

from __future__ import annotations

from audit_service.api.v1.endpoints.audit_events import router as query_router
from audit_service.api.v1.endpoints.health import router as health_router
from audit_service.api.v1.endpoints.internal import router as internal_router

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(internal_router)
api_router.include_router(query_router)
