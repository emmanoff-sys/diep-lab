"""Unit tests — RBAC enforcement dependencies (WP-005-02 / SRS §RBAC)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from identity_service.core.rbac import RequirePermission, RequireRole


def _make_user(role_names: list[str], perm_slugs: list[str]) -> object:
    """Build a mock User with the given roles and permissions."""
    perms = []
    for slug in perm_slugs:
        domain, action = slug.split(":", 1)
        p = MagicMock()
        p.slug = slug
        p.domain = domain
        p.action = action
        perms.append(p)

    roles = []
    for name in role_names:
        r = MagicMock()
        r.name = name
        r.permissions = perms
        roles.append(r)

    user = MagicMock()
    user.roles = roles
    return user


# ---------------------------------------------------------------------------
# RequirePermission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_permission_passes_with_correct_perm() -> None:
    dep = RequirePermission("admin:read")
    user = _make_user(["admin"], ["admin:read", "admin:write"])
    result = await dep(user)  # type: ignore[arg-type]
    assert result is user


@pytest.mark.asyncio
async def test_require_permission_raises_403_when_missing() -> None:
    dep = RequirePermission("admin:write")
    user = _make_user(["customer"], ["own:read"])
    with pytest.raises(HTTPException) as exc_info:
        await dep(user)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_all_perms_must_be_present() -> None:
    dep = RequirePermission("admin:read", "admin:write")
    user = _make_user(["partial"], ["admin:read"])  # missing admin:write
    with pytest.raises(HTTPException) as exc_info:
        await dep(user)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_aggregates_across_roles() -> None:
    dep = RequirePermission("admin:read", "energy:read")
    # User has two roles, each with different permissions
    user = _make_user([], [])
    role_a = MagicMock()
    role_a.name = "admin"
    perm_a = MagicMock()
    perm_a.slug = "admin:read"
    role_a.permissions = [perm_a]

    role_b = MagicMock()
    role_b.name = "engineer"
    perm_b = MagicMock()
    perm_b.slug = "energy:read"
    role_b.permissions = [perm_b]

    user.roles = [role_a, role_b]  # type: ignore[attr-defined]
    result = await dep(user)  # type: ignore[arg-type]
    assert result is user


@pytest.mark.asyncio
async def test_require_permission_empty_required_always_passes() -> None:
    dep = RequirePermission()  # no permissions required
    user = _make_user([], [])
    result = await dep(user)  # type: ignore[arg-type]
    assert result is user


# ---------------------------------------------------------------------------
# RequireRole
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_role_passes_when_has_role() -> None:
    dep = RequireRole("admin")
    user = _make_user(["admin", "customer"], [])
    result = await dep(user)  # type: ignore[arg-type]
    assert result is user


@pytest.mark.asyncio
async def test_require_role_raises_403_when_missing() -> None:
    dep = RequireRole("superadmin")
    user = _make_user(["customer"], [])
    with pytest.raises(HTTPException) as exc_info:
        await dep(user)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_or_semantics() -> None:
    dep = RequireRole("admin", "superadmin")
    user = _make_user(["superadmin"], [])  # not admin but satisfies OR
    result = await dep(user)  # type: ignore[arg-type]
    assert result is user


@pytest.mark.asyncio
async def test_require_role_no_roles_user_denied() -> None:
    dep = RequireRole("admin")
    user = _make_user([], [])
    with pytest.raises(HTTPException) as exc_info:
        await dep(user)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403
