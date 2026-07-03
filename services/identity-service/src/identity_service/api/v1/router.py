"""API v1 router assembly."""

from __future__ import annotations

from fastapi import APIRouter

from identity_service.api.v1 import auth, jwks, roles, users_admin

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(jwks.router)
api_router.include_router(roles.router)
api_router.include_router(users_admin.router)
