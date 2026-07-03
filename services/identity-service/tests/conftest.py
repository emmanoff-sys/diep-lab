"""Shared fixtures for identity-service tests.

Integration tests use testcontainers for real Postgres + Redis.
Unit tests use in-memory / mock substitutes.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing settings
os.environ.setdefault("IDENTITY_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("IDENTITY_REDIS_URL", "redis://localhost:6379/0")


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
