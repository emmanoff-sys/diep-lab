"""Redis-backed account lockout (SRS SEC-001 — 5 failures within TTL window).

Key scheme:
  lockout:fail:{identifier}    — INCR counter, TTL=LOCKOUT_TTL_SECONDS (1800s)
  lockout:blocked:{identifier} — exists = account locked, TTL=LOCKOUT_TTL_SECONDS

`identifier` is the lower-cased email address.  Username is not used as
identifier to prevent username enumeration through lockout timing.
"""

from __future__ import annotations

import redis.asyncio as aioredis

_FAIL_PREFIX = "lockout:fail:"
_BLOCKED_PREFIX = "lockout:blocked:"


async def is_blocked(redis: aioredis.Redis, identifier: str) -> bool:  # type: ignore[type-arg]
    return bool(await redis.exists(f"{_BLOCKED_PREFIX}{identifier.lower()}"))


async def record_failure(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    identifier: str,
    max_failures: int,
    ttl: int,
) -> bool:
    """Increment failure counter.  Returns True if account is now locked."""
    key = f"{_FAIL_PREFIX}{identifier.lower()}"
    count = await redis.incr(key)
    if count == 1:
        # Set TTL only on first failure — window resets if TTL elapses with no new failure
        await redis.expire(key, ttl)
    if count >= max_failures:
        blocked_key = f"{_BLOCKED_PREFIX}{identifier.lower()}"
        await redis.set(blocked_key, "1", ex=ttl)
        return True
    return False


async def clear_failures(redis: aioredis.Redis, identifier: str) -> None:  # type: ignore[type-arg]
    """Clear lockout state on successful authentication."""
    await redis.delete(
        f"{_FAIL_PREFIX}{identifier.lower()}",
        f"{_BLOCKED_PREFIX}{identifier.lower()}",
    )
