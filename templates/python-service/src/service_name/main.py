from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from service_name.api.v1.endpoints import health
from service_name.core.logging import configure_logging

__all__ = ["app", "create_app"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Service Name",
        description="DAEP / RE-OS service — update title and description before deploying.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(health.router, prefix="/health", tags=["health"])
    return application


app = create_app()
