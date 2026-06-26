"""Tests for services/opcua/client.py using a fake asyncua-shaped Client
injected via `client_factory` — asyncua itself is not installed in this dev
environment (see VALIDATION.md), so this exercises OpcUaConnection's own
orchestration logic (backoff, namespace resolution, security wiring,
lifecycle bookkeeping) against the documented asyncua surface, not the real
library's internals."""
import asyncio

import pytest

from services.opcua.client import OpcUaConnection
from services.opcua.config import Settings
from services.opcua.mapping import ServerMapping, SubscriptionMapping
from services.opcua.security import SecurityConfig


def _server(name="p1", url="opc.tcp://p1:4840/"):
    return ServerMapping(name=name, endpoint_url=url, subscriptions=[SubscriptionMapping(node="ns=2;s=X", measurement="x")])


class FakeNode:
    def __init__(self, node_id):
        self._node_id = node_id

    async def read_browse_name(self):
        return "Server"


class FakeClient:
    def __init__(self, url):
        self.url = url
        self.connected = False
        self.should_fail = False
        self.security_string = None
        self.user = None
        self.password = None
        self.session_timeout = 3600000

    def set_security_string(self, s):
        self.security_string = s

    def set_user(self, u):
        self.user = u

    def set_password(self, p):
        self.password = p

    async def connect(self):
        if self.should_fail:
            raise ConnectionError("simulated failure")
        self.connected = True
        self.session_timeout = 600000  # server-side cap, matches Phase 0's reference-server finding

    async def disconnect(self):
        self.connected = False

    async def connect_and_get_server_endpoints(self):
        return ["endpoint1", "endpoint2"]

    async def get_namespace_array(self):
        return ["http://opcfoundation.org/UA/", "urn:diep:plant1"]

    def get_node(self, node_id):
        return FakeNode(node_id)


def _always_succeeds_factory(url):
    return FakeClient(url)


def _fail_n_times_factory(n):
    calls = {"count": 0}

    def factory(url):
        calls["count"] += 1
        client = FakeClient(url)
        client.should_fail = calls["count"] <= n
        return client

    factory.calls = calls
    return factory


def test_resolve_node_id_passthrough_for_ns_form():
    conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
    assert conn.resolve_node_id("ns=2;s=Battery.SOC") == "ns=2;s=Battery.SOC"


def test_resolve_node_id_resolves_nsu_form():
    conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
    conn.namespace_index_by_uri = {"urn:diep:plant1": 3}
    assert conn.resolve_node_id("nsu=urn:diep:plant1;s=Solar.Power") == "ns=3;s=Solar.Power"


def test_resolve_node_id_unknown_uri_raises():
    conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
    with pytest.raises(ValueError):
        conn.resolve_node_id("nsu=urn:unknown;s=X")


def test_connect_success_resolves_namespaces_and_updates_session_timeout():
    conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
    asyncio.run(conn.connect())
    assert conn.connected is True
    assert conn.namespace_index_by_uri == {"http://opcfoundation.org/UA/": 0, "urn:diep:plant1": 1}
    assert conn._granted_session_timeout_s == 600.0  # server-capped 600000ms


def test_disconnect_resets_state():
    conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
    asyncio.run(conn.connect())

    async def _seq():
        await conn.disconnect()

    asyncio.run(_seq())
    assert conn.connected is False
    assert conn.client is None


def test_reconnect_with_backoff_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr(Settings, "RECONNECT_INITIAL_DELAY_S", 0.01)
    monkeypatch.setattr(Settings, "RECONNECT_MAX_DELAY_S", 0.02)
    factory = _fail_n_times_factory(2)
    conn = OpcUaConnection(_server(), client_factory=factory)
    asyncio.run(conn.reconnect_with_backoff())
    assert conn.connected is True
    assert conn.reconnect_count == 1
    assert factory.calls["count"] == 3  # 2 failures + 1 success


def test_reconnect_with_backoff_stops_when_stop_event_set():
    async def _run():
        stop_event = asyncio.Event()
        stop_event.set()
        factory = _fail_n_times_factory(999)
        conn = OpcUaConnection(_server(), client_factory=factory)
        await conn.reconnect_with_backoff(stop_event)
        return conn.connected, factory.calls["count"]

    connected, calls = asyncio.run(_run())
    assert connected is False
    assert calls == 0  # loop never attempted a connect — stop_event was already set


def test_discover_endpoints_uses_factory():
    conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
    endpoints = asyncio.run(conn.discover_endpoints())
    assert endpoints == ["endpoint1", "endpoint2"]


def test_apply_security_none_policy_is_noop():
    conn = OpcUaConnection(_server(), security=None, client_factory=_always_succeeds_factory)
    asyncio.run(conn.connect())
    assert conn.client.security_string is None
    assert conn.client.user is None


def test_apply_security_sets_string_and_credentials():
    sec = SecurityConfig(policy="Basic256Sha256", mode="SignAndEncrypt", cert_path="/c.pem", key_path="/k.pem",
                          username="opcua-user", password="secret")
    conn = OpcUaConnection(_server(), security=sec, client_factory=_always_succeeds_factory)
    asyncio.run(conn.connect())
    assert conn.client.security_string == "Basic256Sha256,SignAndEncrypt,/c.pem,/k.pem"
    assert conn.client.user == "opcua-user"
    assert conn.client.password == "secret"


def test_session_renewal_loop_does_not_crash_without_asyncua_installed():
    """asyncua is not installed in this dev environment, so
    `start_session_renewal_loop`'s `from asyncua import ua` will fail on its
    first scheduled renewal — this asserts that failure is caught and the
    task exits quietly (per its own try/except) rather than crashing the
    event loop or `disconnect()`. The actual renewal call (would it succeed
    against a real server) is unverified here — see VALIDATION.md."""
    async def _run():
        conn = OpcUaConnection(_server(), client_factory=_always_succeeds_factory)
        await conn.connect()
        conn._granted_session_timeout_s = Settings.SESSION_RENEWAL_MARGIN_S + 0.05  # renew almost immediately
        conn.start_session_renewal_loop()
        await asyncio.sleep(0.15)
        await conn.disconnect()  # must not raise even though the renewal task already exited on its own

    asyncio.run(_run())
