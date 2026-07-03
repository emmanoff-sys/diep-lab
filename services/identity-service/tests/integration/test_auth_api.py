"""Integration tests — auth API with real Postgres + Redis via testcontainers.

Covers the full PKCE flow:
  register → login (get auth_code) → token (exchange code+verifier) → refresh → revoke
"""

from __future__ import annotations

import hashlib
import json
import os
from base64 import urlsafe_b64encode
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# These tests require IDENTITY_DATABASE_URL and IDENTITY_REDIS_URL set by
# testcontainers (see conftest_integration.py or CI service containers).
pytestmark = pytest.mark.integration


def _make_pkce_pair() -> tuple[str, str]:
    verifier = "TestVerifier-" + "x" * 30  # 43 chars total
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Spin up the FastAPI app with a test database (injected via env)."""
    from identity_service.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient) -> None:
    payload = {
        "email": f"test-{uuid4()}@example.com",
        "username": f"user{uuid4().hex[:8]}",
        "password": "Str0ng!Password",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == payload["email"]
    assert "customer" in body["roles"]


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    email = f"dup-{uuid4()}@example.com"
    payload = {"email": email, "username": f"u{uuid4().hex[:8]}", "password": "Str0ng!Password"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": f"u{uuid4().hex[:8]}", "password": "Str0ng!Password"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_full_pkce_token_flow(client: AsyncClient) -> None:
    verifier, challenge = _make_pkce_pair()
    email = f"pkce-{uuid4()}@example.com"
    username = f"pkce{uuid4().hex[:8]}"

    # 1. Register
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "Str0ng!Password"},
    )

    # 2. Login → auth code
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": email,
            "password": "Str0ng!Password",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "client_id": "reos-web",
            "client_type": "web",
        },
    )
    assert resp.status_code == 200
    code = resp.json()["code"]
    assert code

    # 3. Exchange code + verifier → tokens
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": "reos-web",
        },
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] == 900

    # 4. Auth code is single-use — second exchange must fail
    resp2 = await client.post(
        "/api/v1/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": "reos-web",
        },
    )
    assert resp2.status_code == 400

    # 5. Refresh
    resp = await client.post(
        "/api/v1/auth/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != tokens["access_token"]

    # 6. Old refresh token is revoked (single-use rotation)
    resp3 = await client.post(
        "/api/v1/auth/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
    )
    assert resp3.status_code == 400


@pytest.mark.asyncio
async def test_wrong_code_verifier_rejected(client: AsyncClient) -> None:
    verifier, challenge = _make_pkce_pair()
    email = f"cv-{uuid4()}@example.com"
    username = f"cv{uuid4().hex[:8]}"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "Str0ng!Password"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": email,
            "password": "Str0ng!Password",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "client_id": "reos-web",
            "client_type": "web",
        },
    )
    code = login_resp.json()["code"]
    wrong_verifier = "w" * 43
    resp = await client.post(
        "/api/v1/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": wrong_verifier,
            "client_id": "reos-web",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_jwks_returns_rsa_key(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/.well-known/jwks.json")
    assert resp.status_code == 200
    jwks = resp.json()
    assert len(jwks["keys"]) >= 1
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert "n" in key
    assert "e" in key


@pytest.mark.asyncio
async def test_revoke_refresh_token(client: AsyncClient) -> None:
    verifier, challenge = _make_pkce_pair()
    email = f"rv-{uuid4()}@example.com"
    username = f"rv{uuid4().hex[:8]}"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "Str0ng!Password"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": email,
            "password": "Str0ng!Password",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "client_id": "reos-web",
            "client_type": "web",
        },
    )
    code = login.json()["code"]
    tkn = await client.post(
        "/api/v1/auth/token",
        data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
              "client_id": "reos-web"},
    )
    rt = tkn.json()["refresh_token"]

    rev = await client.post("/api/v1/auth/revoke", data={"token": rt})
    assert rev.status_code == 204

    # Revoked token must fail
    resp = await client.post(
        "/api/v1/auth/token",
        data={"grant_type": "refresh_token", "refresh_token": rt},
    )
    assert resp.status_code == 400
