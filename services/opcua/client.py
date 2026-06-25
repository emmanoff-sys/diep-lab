"""OPC UA Phase 1/3 — connection lifecycle: endpoint discovery, connect/
disconnect, reconnect-with-backoff, namespace resolution, session renewal,
security application.

`asyncua` is imported lazily, only inside the methods that need it (same
convention as the rest of this codebase for optional/heavy dependencies —
see services/mdm/mqtt_io.py) — this module stays importable, and its pure
logic (backoff math, namespace-URI resolution, config wiring) stays testable,
without asyncua installed. The default `_client_factory` is overridable so
tests can inject a fake asyncua-shaped `Client` — see VALIDATION.md for what
is real vs. fake-verified.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .config import Settings
from .mapping import ServerMapping
from .security import SecurityConfig, build_security_string

logger = logging.getLogger("diep-opcua.client")


class OpcUaConnection:
    def __init__(self, server: ServerMapping, security: SecurityConfig | None = None,
                 cert_store=None, metrics=None, client_factory=None):
        self.server = server
        self.security = security
        self.cert_store = cert_store
        self.metrics = metrics
        self._client_factory = client_factory or self._default_client_factory
        self.client = None
        self.connected = False
        self.namespace_index_by_uri: dict[str, int] = {}
        self._connected_since: float | None = None
        self._granted_session_timeout_s: float = Settings.REQUESTED_SESSION_TIMEOUT_MS / 1000
        self._renewal_task: asyncio.Task | None = None
        self.reconnect_count = 0

        if self.metrics:
            self.metrics.connection_uptime_seconds.labels(server=self.server.name).set_function(
                lambda: (time.monotonic() - self._connected_since) if self._connected_since else 0.0
            )

    @staticmethod
    def _default_client_factory(endpoint_url: str):
        from asyncua import Client
        return Client(url=endpoint_url)

    async def discover_endpoints(self):
        """GetEndpoints discovery (Phase 1). Per asyncua's documented
        connect-for-discovery pattern: opens a transport-level connection,
        runs GetEndpoints, then tears it down without a session."""
        client = self._client_factory(self.server.endpoint_url)
        return await client.connect_and_get_server_endpoints()

    def _apply_security(self, client) -> None:
        if not self.security or self.security.policy == "None":
            return
        security_string = build_security_string(self.security)
        if security_string:
            client.set_security_string(security_string)
        if self.security.username:
            client.set_user(self.security.username)
            if self.security.password:
                client.set_password(self.security.password)

    async def connect(self) -> None:
        client = self._client_factory(self.server.endpoint_url)
        self._apply_security(client)
        client.session_timeout = Settings.REQUESTED_SESSION_TIMEOUT_MS
        await client.connect()
        self.client = client
        self.connected = True
        self._connected_since = time.monotonic()
        granted = getattr(client, "session_timeout", None)
        if granted:
            self._granted_session_timeout_s = granted / 1000
        await self._resolve_namespaces()
        if self.metrics:
            self.metrics.active_sessions.labels(server=self.server.name).set(1)
        logger.info(
            "%s: connected to %s, session_timeout=%.0fs",
            self.server.name, self.server.endpoint_url, self._granted_session_timeout_s,
        )

    async def disconnect(self) -> None:
        if self._renewal_task is not None:
            self._renewal_task.cancel()
            self._renewal_task = None
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception as exc:  # noqa: BLE001 — best-effort on shutdown/error paths
                logger.warning("%s: error during disconnect: %s", self.server.name, exc)
        self.connected = False
        self._connected_since = None
        self.client = None
        if self.metrics:
            self.metrics.active_sessions.labels(server=self.server.name).set(0)

    async def reconnect_with_backoff(self, stop_event: asyncio.Event | None = None) -> None:
        delay = Settings.RECONNECT_INITIAL_DELAY_S
        while stop_event is None or not stop_event.is_set():
            try:
                await self.connect()
                self.reconnect_count += 1
                if self.metrics:
                    self.metrics.reconnect_total.labels(server=self.server.name).inc()
                return
            except Exception as exc:  # noqa: BLE001 — any connect failure should back off and retry, not crash the service
                logger.warning("%s: reconnect attempt failed (%s); retrying in %.1fs", self.server.name, exc, delay)
                await self._sleep_or_stop(stop_event, delay)
                delay = min(delay * Settings.RECONNECT_BACKOFF_FACTOR, Settings.RECONNECT_MAX_DELAY_S)

    @staticmethod
    async def _sleep_or_stop(stop_event: asyncio.Event | None, delay: float) -> None:
        if stop_event is None:
            await asyncio.sleep(delay)
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _resolve_namespaces(self) -> None:
        try:
            ns_array = await self.client.get_namespace_array()
        except Exception as exc:  # noqa: BLE001 — best-effort; ns=<int> node ids still work without this
            logger.warning("%s: failed to read namespace array: %s", self.server.name, exc)
            return
        self.namespace_index_by_uri = {uri: idx for idx, uri in enumerate(ns_array)}

    def resolve_node_id(self, raw: str) -> str:
        """Passes `ns=<int>;...` node ids through unchanged. Resolves
        `nsu=<uri>;...` ids to the *current* numeric namespace index —
        indices aren't guaranteed stable across server restarts, so a
        URI-keyed id is re-resolved on every (re)connect rather than cached
        past one."""
        if not raw.startswith("nsu="):
            return raw
        try:
            uri_part, rest = raw[len("nsu="):].split(";", 1)
        except ValueError:
            raise ValueError(f"malformed namespace-URI node id: {raw!r}")
        idx = self.namespace_index_by_uri.get(uri_part)
        if idx is None:
            raise ValueError(f"namespace URI {uri_part!r} not found on server {self.server.name!r} (node id {raw!r})")
        return f"ns={idx};{rest}"

    def start_session_renewal_loop(self) -> None:
        """"Automatic session renewal" — issues a cheap service call (reading
        the Server object node's BrowseName) before the granted session
        timeout elapses; this both renews server-side session activity and
        doubles as a liveness probe feeding the reconnect path on failure."""
        async def _loop():
            while True:
                interval = max(self._granted_session_timeout_s - Settings.SESSION_RENEWAL_MARGIN_S, 1.0)
                await asyncio.sleep(interval)
                if not self.connected or self.client is None:
                    return
                try:
                    from asyncua import ua
                    node = self.client.get_node(f"i={ua.ObjectIds.Server}")
                    await node.read_browse_name()
                    logger.debug("%s: session renewed", self.server.name)
                except Exception as exc:  # noqa: BLE001 — a failed renewal likely means a dead session; mark disconnected so the worker's poll loop reconnects, but don't crash this task
                    logger.warning("%s: session renewal call failed (%s) — marking disconnected for reconnect", self.server.name, exc)
                    self.connected = False
                    return

        self._renewal_task = asyncio.create_task(_loop())
