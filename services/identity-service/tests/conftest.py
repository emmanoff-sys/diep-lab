"""Shared fixtures for identity-service tests.

Integration tests use testcontainers for real Postgres + Redis.
Unit tests use in-memory / mock substitutes.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# Set required env vars before importing settings
os.environ.setdefault("IDENTITY_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("IDENTITY_REDIS_URL", "redis://localhost:6379/0")

_IDENTITY_DB_MIGRATED = False


@pytest.fixture(scope="session")
def rsa_key_pair() -> tuple[bytes, bytes]:
    """Generate an in-memory RSA-4096 key pair for JWT tests (no Vault needed)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest_asyncio.fixture(autouse=True)
async def identity_integration_runtime(
    request: pytest.FixtureRequest,
    rsa_key_pair: tuple[bytes, bytes],
) -> AsyncGenerator[None, None]:
    """Provide app startup state that ASGITransport does not initialise."""
    if "tests/integration" not in str(request.node.path):
        yield
        return

    import redis.asyncio as aioredis
    from alembic import command
    from alembic.config import Config
    from identity_service.config import settings
    from identity_service.core.jwt import _rsa_public_key_to_jwk, jwt_manager
    from identity_service.db.session import engine
    from identity_service.main import app

    global _IDENTITY_DB_MIGRATED
    if not _IDENTITY_DB_MIGRATED:
        service_dir = Path(__file__).resolve().parents[1]
        alembic_cfg = Config(str(service_dir / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(service_dir / "alembic"))
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        await engine.dispose()
        _IDENTITY_DB_MIGRATED = True

    private_pem, public_pem = rsa_key_pair
    public_key = cast(RSAPublicKey, load_pem_public_key(public_pem))
    jwt_manager._private_key_pem = private_pem
    jwt_manager._public_key_pem = public_pem
    jwt_manager._kid = "test-key-v1"
    jwt_manager._jwks = [_rsa_public_key_to_jwk(public_key, jwt_manager._kid)]

    redis = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    app.state.redis = redis
    await redis.flushdb()
    try:
        yield
    finally:
        await engine.dispose()
        await redis.flushdb()
        await redis.aclose()
        app.state._state.pop("redis", None)
