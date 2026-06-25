"""TTL'd browse-result cache (Phase 2 deliverable) — avoids re-issuing OPC UA
Browse service calls for nodes already browsed recently. Pure stdlib, no
asyncua dependency: callers store whatever node/child representation their
client layer uses; this module only manages expiry.
"""
from __future__ import annotations

import time


class BrowseCache:
    def __init__(self, ttl_s: float = 300.0):
        self._ttl = ttl_s
        self._store: dict[str, tuple[float, object]] = {}

    def get(self, node_id: str):
        entry = self._store.get(node_id)
        if entry is None:
            return None
        stored_at, value = entry
        if time.monotonic() - stored_at > self._ttl:
            del self._store[node_id]
            return None
        return value

    def set(self, node_id: str, value) -> None:
        self._store[node_id] = (time.monotonic(), value)

    def invalidate(self, node_id: str | None = None) -> None:
        """node_id=None clears the whole cache — used on reconnect, since a
        server restart can change browse results (and namespace indices)."""
        if node_id is None:
            self._store.clear()
        else:
            self._store.pop(node_id, None)

    def __len__(self) -> int:
        return len(self._store)
