from __future__ import annotations

import os

import pytest

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def postgres_url() -> str:
    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
    except ImportError:
        pytest.skip("testcontainers not installed — skipping integration test")
    with PostgresContainer("postgres:16-alpine") as pg:
        return str(pg.get_connection_url()).replace("postgresql://", "postgresql+asyncpg://")


def test_app_starts_and_health_reachable(postgres_url: str) -> None:
    """Smoke test: app starts with a real Postgres instance and /health returns 200."""
    os.environ["DATABASE_URL"] = postgres_url
    from service_name.main import create_app  # re-import to pick up env override

    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
