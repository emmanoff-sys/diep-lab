"""JWKS endpoint — publishes RS256 public key for downstream JWT verification (SRS SEC-002)."""

from __future__ import annotations

from identity_service.core.jwt import jwt_manager
from identity_service.schemas.auth import JWKSResponse

from fastapi import APIRouter

router = APIRouter()


@router.get(
    "/.well-known/jwks.json",
    response_model=JWKSResponse,
    tags=["auth"],
    summary="JSON Web Key Set for RS256 token verification",
)
async def get_jwks() -> JWKSResponse:
    return JWKSResponse(keys=jwt_manager.get_jwks())
