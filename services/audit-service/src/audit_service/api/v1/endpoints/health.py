"""Health check endpoints (ENG-SPEC-005-04 §21).

GET /api/v1/health/live   — liveness (no external checks; always 200)
GET /api/v1/health/ready  — readiness (DB + Kafka + JWKS cache)
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from audit_service.config import settings
from audit_service.core import kafka as kafka_core
from audit_service.core.security import jwks_cache

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": settings.SERVICE_VERSION}


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    all_ok = True

    # 1. DB: SELECT 1 against audit schema
    try:
        db_factory = request.app.state.db_session_factory
        async with db_factory() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        all_ok = False

    # 2. Kafka consumer state
    if kafka_core.is_running():
        checks["kafka_consumer"] = "ok"
    else:
        checks["kafka_consumer"] = "error: consumer not running"
        all_ok = False

    # 3. JWKS cache freshness (503 if stale > JWKS_STALE_THRESHOLD_S)
    age = jwks_cache.last_fetch_age_seconds
    if age <= settings.JWKS_STALE_THRESHOLD_S:
        checks["jwks_cache"] = "ok"
    else:
        checks["jwks_cache"] = f"error: last fetch {age:.0f}s ago (threshold {settings.JWKS_STALE_THRESHOLD_S}s)"
        all_ok = False

    body = {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }
    code = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=body)
