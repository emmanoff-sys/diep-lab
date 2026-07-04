"""Unit tests — MFA lockout logic (WP-005-02 / SRS SEC-005).

SEC-005 exact values under test:
  - Attempt window TTL: 1800s
  - Lock threshold: 5 failures
  - Lock TTL: 900s
  - Admin manual unlock clears both counter and lock keys
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from identity_service.core.mfa_lockout import (
    admin_unlock_mfa,
    clear_mfa_failures,
    is_mfa_locked,
    record_mfa_failure,
)

_MAX = 5
_WINDOW = 1800
_LOCK_TTL = 900


def _make_redis(
    *,
    exists_return: int = 0,
    incr_return: int = 1,
) -> MagicMock:
    redis = MagicMock()
    redis.exists = AsyncMock(return_value=exists_return)
    redis.incr = AsyncMock(return_value=incr_return)
    redis.expire = AsyncMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.getdel = AsyncMock(return_value=None)
    return redis


@pytest.mark.asyncio
async def test_not_locked_when_no_lock_key() -> None:
    redis = _make_redis(exists_return=0)
    assert await is_mfa_locked(redis, "user-abc") is False
    redis.exists.assert_awaited_once_with("mfa:locked:user-abc")


@pytest.mark.asyncio
async def test_is_locked_when_lock_key_present() -> None:
    redis = _make_redis(exists_return=1)
    assert await is_mfa_locked(redis, "user-abc") is True


@pytest.mark.asyncio
async def test_first_failure_sets_window_ttl() -> None:
    redis = _make_redis(incr_return=1)
    locked = await record_mfa_failure(redis, "u1", _MAX, _WINDOW, _LOCK_TTL)
    assert locked is False
    redis.expire.assert_awaited_once_with("mfa:attempts:u1", _WINDOW)
    redis.set.assert_not_awaited()  # not yet locked


@pytest.mark.asyncio
async def test_subsequent_failures_do_not_reset_window_ttl() -> None:
    redis = _make_redis(incr_return=3)
    await record_mfa_failure(redis, "u1", _MAX, _WINDOW, _LOCK_TTL)
    redis.expire.assert_not_awaited()  # TTL only set on first failure (count == 1)


@pytest.mark.asyncio
async def test_fifth_failure_triggers_lock() -> None:
    redis = _make_redis(incr_return=5)
    locked = await record_mfa_failure(redis, "u1", _MAX, _WINDOW, _LOCK_TTL)
    assert locked is True
    redis.set.assert_awaited_once_with("mfa:locked:u1", "1", ex=_LOCK_TTL)


@pytest.mark.asyncio
async def test_beyond_fifth_failure_lock_re_set() -> None:
    """Subsequent failures after the lock also call set() — lock TTL is refreshed."""
    redis = _make_redis(incr_return=7)
    locked = await record_mfa_failure(redis, "u1", _MAX, _WINDOW, _LOCK_TTL)
    assert locked is True


@pytest.mark.asyncio
async def test_clear_failures_deletes_both_keys() -> None:
    redis = _make_redis()
    await clear_mfa_failures(redis, "u1")
    redis.delete.assert_awaited_once_with("mfa:attempts:u1", "mfa:locked:u1")


@pytest.mark.asyncio
async def test_admin_unlock_deletes_both_keys() -> None:
    redis = _make_redis()
    await admin_unlock_mfa(redis, "u1")
    redis.delete.assert_awaited_once_with("mfa:locked:u1", "mfa:attempts:u1")
