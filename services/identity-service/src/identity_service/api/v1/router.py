"""API v1 router assembly."""

from __future__ import annotations

from fastapi import APIRouter

from identity_service.api.v1 import auth, jwks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(jwks.router)
