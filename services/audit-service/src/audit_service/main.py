"""DAEP / RE-OS Audit Service — FastAPI application entry point (WP-005-04).

Lifespan sequence:
  startup:  configure logging → init DB engine → warm JWKS cache
            → start Kafka consumer + DLQ producer
  shutdown: stop Kafka consumer → dispose DB engine
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import structlog
from audit_service.api.v1.router import api_router
from audit_service.config import settings
from audit_service.core import kafka as kafka_core
from audit_service.core import logging as log_module
from audit_service.core.security import jwks_cache
from audit_service.db.session import create_engine_and_factory
from audit_service.domain.services import AuditService
from sqlalchemy.ext.asyncio import AsyncEngine

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log_module.configure(settings.LOG_LEVEL)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    engine, session_factory = create_engine_and_factory()
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    # Warm JWKS cache — non-fatal if identity-service not yet up
    try:
        await jwks_cache.get_keys()
    except Exception:
        logger.warning("startup.jwks_warm_failed — will retry on first request")

    # Start Kafka consumer; write_event closure captures session_factory
    async def _write_event_fn(event_data: object, source: str = "kafka") -> None:
        async with session_factory() as session:
            svc = AuditService(session)
            await svc.write_event(event_data, source=source)  # type: ignore[arg-type]

    await kafka_core.start_consumer(_write_event_fn)

    logger.info("audit_service.started", port=settings.PORT, version=settings.SERVICE_VERSION)
    yield

    await kafka_core.stop_consumer()
    await cast(AsyncEngine, engine).dispose()
    logger.info("audit_service.stopped")


app = FastAPI(
    title="DAEP / RE-OS Audit Service",
    description="Immutable Platform Audit Log (WP-005-04)",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
