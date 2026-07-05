"""DAEP / RE-OS Identity Service — FastAPI application entry point (WP-005-01).

Lifespan sequence:
  startup:  Vault authenticate → fetch RS256 signing key → start Kafka producer → init Redis
  shutdown: close Kafka producer → close Vault client → close JWT manager
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from identity_service.api.v1.health import router as health_router
from identity_service.api.v1.router import api_router
from identity_service.config import settings
from identity_service.core import kafka
from identity_service.core.jwt import jwt_manager
from identity_service.core.vault import VaultClient

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    vault = VaultClient()
    try:
        await jwt_manager.initialise(vault)
    except Exception:
        logger.exception("startup.vault_init_failed")
        raise

    await kafka.start_producer()

    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.vault = vault

    logger.info("identity_service.started", port=settings.PORT)
    yield

    await kafka.stop_producer()
    await jwt_manager.close()
    await vault.close()
    await app.state.redis.aclose()
    logger.info("identity_service.stopped")


app = FastAPI(
    title="DAEP / RE-OS Identity Service",
    description="OAuth2 PKCE + RS256 JWT + RBAC (WP-005-01)",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(api_router)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
