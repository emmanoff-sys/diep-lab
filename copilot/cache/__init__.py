"""Cache abstraction for the Copilot service.

Provides cache_get, cache_set, cache_delete utilities backed by Redis
with configurable TTL. Cache keys are SHA256 hashes of tenant_id, endpoint,
and normalized request body to ensure isolation and prevent collisions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("diep-copilot.cache")

# Default TTL for cache entries (seconds).
DEFAULT_TTL: int = 300


def _make_cache_key(
    tenant: str | None,
    endpoint: str,
    body: dict[str, Any] | None = None,
) -> str:
    """Generate a deterministic SHA256 cache key.

    The key incorporates tenant_id for isolation, endpoint path to scope the
    cache, and the normalized request body for uniqueness.

    Args:
        tenant: Tenant ID from JWT (or ``"__global__"`` for admin).
        endpoint: The endpoint path (e.g., ``/copilot/fleet_health``).
        body: Optional request body dict (for POST endpoints).

    Returns:
        Hex-encoded SHA256 digest.
    """
    tenant_str = tenant or "__global__"
    body_str = json.dumps(body, sort_keys=True, separators=(",", ":")) if body else ""
    raw = f"{tenant_str}|{endpoint}|{body_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(
    redis_client: Any,
    key: str,
) -> str | None:
    """Retrieve a cached value by its SHA256 key.

    Args:
        redis_client: A Redis client instance (``redis.Redis`` or compatible).
        key: The hex-encoded SHA256 cache key.

    Returns:
        The cached JSON string, or ``None`` if the key does not exist or
        Redis is unreachable.
    """
    try:
        value = redis_client.get(f"cache:{key}")
        if value is not None:
            logger.debug("Cache HIT for key cache:%s", key)
            return value
        logger.debug("Cache MISS for key cache:%s", key)
        return None
    except Exception as exc:
        logger.warning("Cache get failed for key cache:%s: %s", key, exc)
        return None


def cache_set(
    redis_client: Any,
    key: str,
    value: str,
    ttl: int = DEFAULT_TTL,
) -> bool:
    """Store a value in the cache with a TTL.

    Args:
        redis_client: A Redis client instance.
        key: The hex-encoded SHA256 cache key.
        value: The JSON string to cache.
        ttl: Time-to-live in seconds (default: 300).

    Returns:
        ``True`` if the value was stored successfully, ``False`` otherwise.
    """
    try:
        redis_client.setex(f"cache:{key}", ttl, value)
        logger.debug("Cache SET for key cache:%s (TTL=%ds)", key, ttl)
        return True
    except Exception as exc:
        logger.warning("Cache set failed for key cache:%s: %s", key, exc)
        return False


def cache_delete(
    redis_client: Any,
    key: str,
) -> bool:
    """Delete a single cache entry.

    Args:
        redis_client: A Redis client instance.
        key: The hex-encoded SHA256 cache key.

    Returns:
        ``True`` if the key was deleted, ``False`` if it did not exist or on error.
    """
    try:
        result = redis_client.delete(f"cache:{key}")
        if result:
            logger.debug("Cache DELETED for key cache:%s", key)
        return bool(result)
    except Exception as exc:
        logger.warning("Cache delete failed for key cache:%s: %s", key, exc)
        return False


def cache_flush_all(
    redis_client: Any,
) -> bool:
    """Delete ALL Copilot cache entries (development/debugging only).

    WARNING: This scans for ``cache:*`` keys and deletes them. Not recommended
    for production use with large caches.

    Args:
        redis_client: A Redis client instance.

    Returns:
        ``True`` if the flush completed (or no keys found).
    """
    try:
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match="cache:*", count=100)
            if keys:
                redis_client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        logger.info("Cache flush complete: %d keys deleted", deleted)
        return True
    except Exception as exc:
        logger.warning("Cache flush failed: %s", exc)
        return False


__all__ = [
    "_make_cache_key",
    "cache_get",
    "cache_set",
    "cache_delete",
    "cache_flush_all",
    "DEFAULT_TTL",
]