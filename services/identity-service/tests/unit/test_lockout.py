"""Unit tests — Redis-backed account lockout (SRS SEC-001)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from identity_service.core.lockout import clear_failures, is_blocked, record_failure

_IDENTIFIER = "user@example.com"
_MAX = 5
_TTL = 1800


def _make_redis(**kw: object) -> AsyncMock:
    r = AsyncMock()
    for attr, val in kw.items():
        setattr(r, attr, AsyncMock(return_value=val))
    return r


@pytest.mark.asyncio
async def test_not_blocked_initially() -> None:
    redis = _make_redis(exists=0)
    assert not await is_blocked(redis, _IDENTIFIER)


@pytest.mark.asyncio
async def test_blocked_after_max_failures() -> None:
    redis = _make_redis(incr=_MAX, expire=None, set=None)
    blocked = await record_failure(redis, _IDENTIFIER, _MAX, _TTL)
    assert blocked
    redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_not_blocked_before_max() -> None:
    redis = _make_redis(incr=3, expire=None)
    blocked = await record_failure(redis, _IDENTIFIER, _MAX, _TTL)
    assert not blocked


@pytest.mark.asyncio
async def test_expire_set_on_first_failure() -> None:
    redis = _make_redis(incr=1, expire=None)
    await record_failure(redis, _IDENTIFIER, _MAX, _TTL)
    redis.expire.assert_called_once_with(f"lockout:fail:{_IDENTIFIER}", _TTL)


@pytest.mark.asyncio
async def test_expire_not_reset_on_subsequent_failures() -> None:
    redis = _make_redis(incr=2, expire=None)
    await record_failure(redis, _IDENTIFIER, _MAX, _TTL)
    redis.expire.assert_not_called()


@pytest.mark.asyncio
async def test_clear_failures() -> None:
    redis = _make_redis(delete=2)
    await clear_failures(redis, _IDENTIFIER)
    redis.delete.assert_called_once_with(
        f"lockout:fail:{_IDENTIFIER}",
        f"lockout:blocked:{_IDENTIFIER}",
    )


@pytest.mark.asyncio
async def test_identifier_lowercased() -> None:
    redis = _make_redis(exists=0)
    await is_blocked(redis, "USER@EXAMPLE.COM")
    redis.exists.assert_called_once_with("lockout:blocked:user@example.com")
