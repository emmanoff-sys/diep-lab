"""Unit tests for ``cache`` module."""

from __future__ import annotations

import json
import hashlib
from unittest.mock import MagicMock, patch

import pytest

from copilot.cache import (
    _make_cache_key,
    cache_get,
    cache_set,
    cache_delete,
    cache_flush_all,
    DEFAULT_TTL,
)
from copilot.cache.redis_cache import RedisCache


class TestMakeCacheKey:
    """Tests for ``_make_cache_key()``."""

    def test_deterministic_with_same_inputs(self) -> None:
        key1 = _make_cache_key("acme", "/copilot/fleet_health")
        key2 = _make_cache_key("acme", "/copilot/fleet_health")
        assert key1 == key2

    def test_different_tenants_produce_different_keys(self) -> None:
        key_a = _make_cache_key("acme", "/copilot/fleet_health")
        key_b = _make_cache_key("globex", "/copilot/fleet_health")
        assert key_a != key_b

    def test_different_endpoints_produce_different_keys(self) -> None:
        key1 = _make_cache_key("acme", "/copilot/fleet_health")
        key2 = _make_cache_key("acme", "/copilot/site_health")
        assert key1 != key2

    def test_body_included_in_key(self) -> None:
        key1 = _make_cache_key("acme", "/copilot/explain_alarm", body={"alarm_id": 42})
        key2 = _make_cache_key("acme", "/copilot/explain_alarm", body={"alarm_id": 99})
        assert key1 != key2

    def test_global_tenant_key(self) -> None:
        key = _make_cache_key(None, "/copilot/fleet_health")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex digest

    def test_key_is_sha256_hex(self) -> None:
        key = _make_cache_key("acme", "/copilot/fleet_health")
        assert len(key) == 64
        # Verify it's a valid hex string
        int(key, 16)

    def test_sorted_body_keys(self) -> None:
        """Body dicts with same keys in different order should produce same key."""
        key1 = _make_cache_key("acme", "/copilot/endpoint", body={"b": 2, "a": 1})
        key2 = _make_cache_key("acme", "/copilot/endpoint", body={"a": 1, "b": 2})
        assert key1 == key2

    def test_none_body(self) -> None:
        key = _make_cache_key("acme", "/copilot/fleet_health", body=None)
        assert isinstance(key, str) and len(key) == 64


class TestCacheGetSetDelete:
    """Tests for cache_get/cache_set/cache_delete with a mock Redis client."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        return MagicMock()

    def test_cache_get_hit(self, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = '{"answer": "test"}'
        result = cache_get(mock_redis, "abc123")
        assert result == '{"answer": "test"}'
        mock_redis.get.assert_called_once_with("cache:abc123")

    def test_cache_get_miss(self, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = None
        result = cache_get(mock_redis, "abc123")
        assert result is None

    def test_cache_get_error_returns_none(self, mock_redis: MagicMock) -> None:
        mock_redis.get.side_effect = ConnectionError("Redis down")
        result = cache_get(mock_redis, "abc123")
        assert result is None

    def test_cache_set_success(self, mock_redis: MagicMock) -> None:
        mock_redis.setex.return_value = True
        result = cache_set(mock_redis, "abc123", '{"answer": "test"}', ttl=300)
        assert result is True
        mock_redis.setex.assert_called_once_with(
            "cache:abc123", 300, '{"answer": "test"}'
        )

    def test_cache_set_uses_default_ttl(self, mock_redis: MagicMock) -> None:
        mock_redis.setex.return_value = True
        result = cache_set(mock_redis, "abc123", "value")
        assert result is True
        mock_redis.setex.assert_called_once_with(
            "cache:abc123", DEFAULT_TTL, "value"
        )

    def test_cache_set_error_returns_false(self, mock_redis: MagicMock) -> None:
        mock_redis.setex.side_effect = ConnectionError("Redis down")
        result = cache_set(mock_redis, "abc123", "value")
        assert result is False

    def test_cache_delete_existing_key(self, mock_redis: MagicMock) -> None:
        mock_redis.delete.return_value = 1
        result = cache_delete(mock_redis, "abc123")
        assert result is True

    def test_cache_delete_nonexistent_key(self, mock_redis: MagicMock) -> None:
        mock_redis.delete.return_value = 0
        result = cache_delete(mock_redis, "abc123")
        assert result is False

    def test_cache_delete_error_returns_false(self, mock_redis: MagicMock) -> None:
        mock_redis.delete.side_effect = ConnectionError("Redis down")
        result = cache_delete(mock_redis, "abc123")
        assert result is False

    def test_cache_flush_success(self, mock_redis: MagicMock) -> None:
        # Simulate two SCAN iterations
        mock_redis.scan.side_effect = [
            (1, ["cache:key1", "cache:key2"]),
            (0, ["cache:key3"]),
        ]
        mock_redis.delete.return_value = 3
        result = cache_flush_all(mock_redis)
        assert result is True
        assert mock_redis.delete.call_count == 2


class TestRedisCache:
    """Tests for ``RedisCache`` class."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def cache(self, mock_redis: MagicMock) -> RedisCache:
        return RedisCache(mock_redis, default_ttl=300)

    def test_get_returns_cached_value(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = '{"answer": "test"}'
        result = cache.get("acme", "/copilot/fleet_health")
        assert result == '{"answer": "test"}'

    def test_get_returns_none_on_miss(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = None
        result = cache.get("acme", "/copilot/fleet_health")
        assert result is None

    def test_set_stores_value(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.setex.return_value = True
        result = cache.set("acme", "/copilot/fleet_health", '{"answer": "test"}')
        assert result is True

    def test_get_or_compute_cache_hit(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = '{"answer": "cached"}'
        result, hit = cache.get_or_compute(
            "acme",
            "/copilot/fleet_health",
            compute_fn=lambda: '{"answer": "fresh"}',
        )
        assert result == '{"answer": "cached"}'
        assert hit is True

    def test_get_or_compute_cache_miss(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        result, hit = cache.get_or_compute(
            "acme",
            "/copilot/fleet_health",
            compute_fn=lambda: '{"answer": "fresh"}',
        )
        assert result == '{"answer": "fresh"}'
        assert hit is False
        # Should have stored the computed value
        assert mock_redis.setex.called

    def test_delete_evicts_entry(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.delete.return_value = 1
        result = cache.delete("acme", "/copilot/fleet_health")
        assert result is True

    def test_flush_all(self, cache: RedisCache, mock_redis: MagicMock) -> None:
        mock_redis.scan.return_value = (0, [])
        result = cache.flush_all()
        assert result is True