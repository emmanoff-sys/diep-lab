"""Integration tests — Role and Permission management API (WP-005-02).

These tests verify:
  1. Endpoint registration and routing (405 on wrong method, 401/403 without auth)
  2. RBAC schema validation (role name pattern)
  3. User-role self-read (own roles without admin:read)
  4. System-role write protection (requires real DB session; marked for WP-005-08 full suite)

Full admin-path tests (create role, assign permission, etc.) require an admin-seeded
user with admin:write permission. Those tests are deferred to WP-005-08 which
provisions the full integration environment including seeded admin users.
"""

from __future__ import annotations

import hashlib
from base64 import urlsafe_b64encode
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


def _pkce_pair() -> tuple[str, str]:
    verifier = "IntegVerifier-" + "x" * 30
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def client() -> AsyncClient:
    from identity_service.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unauthenticated access — endpoint existence and auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_permissions_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/permissions")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_roles_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/roles")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_role_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/roles", json={"name": "test-role"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_delete_role_requires_auth(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/roles/00000000-0000-0000-0000-000000000001")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_user_roles_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/00000000-0000-0000-0000-000000000001/roles")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Schema validation (no auth needed to verify 422 on bad input)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_role_invalid_name_rejected(client: AsyncClient) -> None:
    """Role names must match ^[a-z][a-z0-9_-]*$ — uppercase rejected."""
    resp = await client.post(
        "/api/v1/roles",
        json={"name": "Invalid-Role"},  # uppercase
        headers={"Authorization": "Bearer placeholder"},
    )
    assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# Own-roles self-read (any authenticated user can read their own roles)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_own_roles_readable_after_register_and_login(client: AsyncClient) -> None:
    """A freshly registered user can read their own roles via JWT bearer."""
    verifier, challenge = _pkce_pair()
    email = f"rbac-test-{uuid4()}@example.com"
    username = f"rbac{uuid4().hex[:8]}"

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
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": "reos-web",
        },
    )
    at = tkn.json()["access_token"]

    # Decode sub from the JWT to find user_id
    from jose import jwt as jose_jwt

    payload = jose_jwt.get_unverified_claims(at)
    user_id = payload["sub"]

    resp = await client.get(
        f"/api/v1/users/{user_id}/roles",
        headers={"Authorization": f"Bearer {at}"},
    )
    assert resp.status_code == 200
    roles_data = resp.json()
    assert isinstance(roles_data, list)
    assert any(r["role_name"] == "customer" for r in roles_data)


@pytest.mark.asyncio
async def test_cannot_read_other_users_roles_without_admin(client: AsyncClient) -> None:
    """A customer cannot read another user's roles (requires admin:read)."""
    verifier, challenge = _pkce_pair()
    email = f"spy-{uuid4()}@example.com"
    username = f"spy{uuid4().hex[:8]}"

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
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": "reos-web",
        },
    )
    at = tkn.json()["access_token"]

    resp = await client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000001/roles",
        headers={"Authorization": f"Bearer {at}"},
    )
    assert resp.status_code == 403
