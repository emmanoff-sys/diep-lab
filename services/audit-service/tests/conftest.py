"""Integration test fixtures — real PostgreSQL (TimescaleDB) via testcontainers.

STANDARDS.md §7: integration tests MUST use a real DB. No DB mocking.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from audit_service.domain.models import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Attempt testcontainers; skip integration tests if not available in CI
try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import]

    HAS_CONTAINERS = True
except ImportError:
    HAS_CONTAINERS = False


TIMESCALE_IMAGE = "timescale/timescaledb:latest-pg15"


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_container():  # type: ignore[return]
    if not HAS_CONTAINERS:
        pytest.skip("testcontainers not available")
    with PostgresContainer(TIMESCALE_IMAGE) as pg:
        yield pg


@pytest.fixture
async def db_engine(pg_container):  # type: ignore[return]
    url = pg_container.get_connection_url(driver="asyncpg")
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS audit"))
        await conn.run_sync(Base.metadata.create_all)
        # TimescaleDB extension and hypertable (test env)
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            await conn.execute(
                text(
                    "SELECT create_hypertable('audit.audit_events', 'timestamp_utc',"
                    " chunk_time_interval => INTERVAL '1 month', if_not_exists => TRUE)"
                )
            )
        except Exception:  # noqa: S110 — TimescaleDB hypertable is optional in non-TimescaleDB CI
            pass

    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:  # type: ignore[return]
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def base_event_data() -> dict[str, object]:
    return {
        "event_id": uuid4(),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": uuid4(),
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": uuid4(),
        "service_name": "identity-service",
        "timestamp_utc": datetime.now(UTC),
        "schema_version": 1,
    }
