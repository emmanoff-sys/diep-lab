"""Tests for services/opcua/browse_cache.py — pure stdlib."""
import time

from services.opcua.browse_cache import BrowseCache


def test_set_then_get_returns_value():
    cache = BrowseCache(ttl_s=60)
    cache.set("ns=2;s=Folder1", ["child1", "child2"])
    assert cache.get("ns=2;s=Folder1") == ["child1", "child2"]


def test_missing_key_returns_none():
    cache = BrowseCache()
    assert cache.get("nope") is None


def test_ttl_expiry():
    cache = BrowseCache(ttl_s=0.05)
    cache.set("n", ["x"])
    assert cache.get("n") == ["x"]
    time.sleep(0.07)
    assert cache.get("n") is None
    assert len(cache) == 0  # expired entry evicted on read


def test_invalidate_single_key():
    cache = BrowseCache(ttl_s=60)
    cache.set("a", [1])
    cache.set("b", [2])
    cache.invalidate("a")
    assert cache.get("a") is None
    assert cache.get("b") == [2]


def test_invalidate_all():
    cache = BrowseCache(ttl_s=60)
    cache.set("a", [1])
    cache.set("b", [2])
    cache.invalidate()
    assert len(cache) == 0
