"""Redis-backed cache implementation for the Copilot service.

Provides a concrete ``RedisCache`` class that wraps the functional API from
``copilot.cache`` with a Redis client instance. This is the production
implementation used by the Copilot endpoints.

Usage:
    from copilot.cache.redis_cache import RedisCache
    from redis import Redis

    r = Redis(host="diep-redis", port=6379, decode_responses=True)
    cache = RedisCache(r, default_ttl=300)

    # Cache miss → compute and store
    result = cache.get_or_compute(
        tenant="acme",
        endpoint="/copilot/fleet_health",
        compute_fn=lambda: json.dumps({"answer": "...", ...}),
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from copilot.cache import (
    _make_cache_key,
    cache_get,
    cache_set,
    cache_delete,
    cache_flush_all,
    DEFAULT_TTL,
)

logger = logging.getLogger("diep-copilot.redis_cache")


class RedisCache:
    """A Redis-backed cache with automatic key generation and TTL management.

    Args:
        redis_client: A ``redis.Redis`` instance (or compatible).
        default_ttl: Default TTL in seconds for cache entries.
    """

    def __init__(
        self,
        redis_client: Any,
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        self._redis = redis_client
        self._default_ttl = default_ttl

    def get(
        self,
        tenant: str | None,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> str | None:
        """Retrieve a cached response.

        Args:
            tenant: Tenant ID from JWT (or None for global).
            endpoint: The endpoint path.
            body: Optional request body for POST endpoints.

        Returns:
            Cached JSON string, or None if miss.
        """
        key = _make_cache_key(tenant, endpoint, body)
        return cache_get(self._redis, key)

    def set(
        self,
        tenant: str | None,
        endpoint: str,
        value: str,
        body: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> bool:
        """Store a response in the cache.

        Args:
            tenant: Tenant ID from JWT (or None for global).
            endpoint: The endpoint path.
            value: The JSON string to cache.
            body: Optional request body for POST endpoints.
            ttl: Optional TTL override (defaults to ``self._default_ttl``).

        Returns:
            True if stored successfully.
        """
        key = _make_cache_key(tenant, endpoint, body)
        return cache_set(self._redis, key, value, ttl=ttl or self._default_ttl)

    def delete(
        self,
        tenant: str | None,
        endpoint: str,
        body: dict[str, Any] | None = None,
    ) -> bool:
        """Evict a single cache entry.

        Args:
            tenant: Tenant ID from JWT (or None for global).
            endpoint: The endpoint path.
            body: Optional request body for POST endpoints.

        Returns:
            True if the key existed and was deleted.
        """
        key = _make_cache_key(tenant, endpoint, body)
        return cache_delete(self._redis, key)

    def get_or_compute(
        self,
        tenant: str | None,
        endpoint: str,
        compute_fn: Callable[[], str],
        body: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> tuple[str, bool]:
        """Get from cache or compute and store.

        This is the primary entry point for endpoints. It implements the
        cache-aside pattern: check cache first, compute on miss, store result.

        Args:
            tenant: Tenant ID from JWT (or None for global).
            endpoint: The endpoint path.
            compute_fn: A callable that returns the JSON string to cache.
            body: Optional request body for POST endpoints.
            ttl: Optional TTL override.

        Returns:
            Tuple of (json_response_string, was_cache_hit).
        """
        key = _make_cache_key(tenant, endpoint, body)

        # Try cache first.
        cached = cache_get(self._redis, key)
        if cached is not None:
            return cached, True

        # Cache miss — compute.
        fresh = compute_fn()

        # Store asynchronously in background; if it fails, we already have the value.
        cache_set(self._redis, key, fresh, ttl=ttl or self._default_ttl)

        return fresh, False

    def flush_all(self) -> bool:
        """Delete all Copilot cache entries.

        WARNING: Only for development/debugging. Uses SCAN + DELETE.

        Returns:
            True on success.
        """
        return cache_flush_all(self._redis)


__all__ = ["RedisCache"]