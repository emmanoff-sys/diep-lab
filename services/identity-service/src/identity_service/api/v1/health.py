"""Health check endpoint — Consul / load-balancer probe target."""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="identity-service")
