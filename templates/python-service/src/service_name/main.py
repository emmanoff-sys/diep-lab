from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from reos_exceptions import NotFoundError, register_exception_handlers
from service_name.api.v1.endpoints import health
from service_name.config import get_settings
from service_name.core.logging import configure_logging

from fastapi import FastAPI

__all__ = ["app", "create_app"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(get_settings())
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Service Name",
        description="DAEP / RE-OS service — update title and description before deploying.",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(application)
    application.include_router(health.router, prefix="/health", tags=["health"])

    @application.get("/examples/not-found", tags=["examples"], include_in_schema=False)
    async def _example_not_found() -> None:
        """Deliberate RFC 7807 404 demo (WP-002-05 §32) — delete in real services."""
        raise NotFoundError("Example", "always-missing")

    return application


app = create_app()
