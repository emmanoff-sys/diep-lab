from __future__ import annotations

from service_name.api.v1.schemas.health import HealthResponse

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
