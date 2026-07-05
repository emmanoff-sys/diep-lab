"""MFA attempt tracking and lockout (SRS SEC-005).

Key scheme:
  mfa:attempts:{user_id}  — INCR counter, TTL = MFA_LOCKOUT_WINDOW_SECONDS (1800s)
  mfa:locked:{user_id}    — exists = MFA locked, TTL = MFA_LOCKED_TTL_SECONDS (900s)

SEC-005 exact values (not independently configurable without a new ECR):
  - Window: 30 minutes (1800s)
  - Lock threshold: 5 failures
  - Lock TTL: 15 minutes (900s)
  - Admin can unlock manually

Separate from the login lockout (SEC-001 / core/lockout.py), which tracks credential
failures by email/username, not by user_id.
"""

from __future__ import annotations

import redis.asyncio as aioredis

_ATTEMPTS_PREFIX = "mfa:attempts:"
_LOCKED_PREFIX = "mfa:locked:"


async def is_mfa_locked(redis: aioredis.Redis, user_id: str) -> bool:
    return bool(await redis.exists(f"{_LOCKED_PREFIX}{user_id}"))


async def record_mfa_failure(
    redis: aioredis.Redis,
    user_id: str,
    max_attempts: int,
    window_seconds: int,
    lock_ttl: int,
) -> bool:
    """Increment MFA failure counter.  Returns True if account is now MFA-locked."""
    key = f"{_ATTEMPTS_PREFIX}{user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count >= max_attempts:
        locked_key = f"{_LOCKED_PREFIX}{user_id}"
        await redis.set(locked_key, "1", ex=lock_ttl)
        return True
    return False


async def clear_mfa_failures(redis: aioredis.Redis, user_id: str) -> None:
    """Clear MFA lockout state on successful verification."""
    await redis.delete(
        f"{_ATTEMPTS_PREFIX}{user_id}",
        f"{_LOCKED_PREFIX}{user_id}",
    )


async def admin_unlock_mfa(redis: aioredis.Redis, user_id: str) -> None:
    """Admin-initiated manual MFA unlock (SEC-005: admin can unlock manually)."""
    await redis.delete(
        f"{_LOCKED_PREFIX}{user_id}",
        f"{_ATTEMPTS_PREFIX}{user_id}",
    )
