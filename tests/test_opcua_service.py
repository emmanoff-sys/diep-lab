"""Integration tests for services/opcua/service.py's ServerWorker run loop,
using a fake asyncua-shaped client (asyncua is not installed in this dev
environment — see VALIDATION.md). Covers: connect -> subscribe -> graceful
shutdown, and connection-loss -> reconnect (driven by the session renewal
loop marking `connected = False` on failure, per client.py)."""
import asyncio

import pytest

from services.opcua.client import OpcUaConnection
from services.opcua.config import Settings
from services.opcua.mapping import ServerMapping, SubscriptionMapping
from services.opcua.measurement import MeasurementSink
from services.opcua.metrics import OpcuaMetrics
from services.opcua.service import ServerWorker, build_security_config
from services.opcua.subscription import SubscriptionManager


class FakeNodeId:
    def __init__(self, s):
        self._s = s

    def to_string(self):
        return self._s


class FakeNode:
    def __init__(self, node_id):
        self.nodeid = FakeNodeId(node_id)

    async def get_children(self):
        return []


class FakeSubscription:
    def __init__(self):
        self.calls = []

    async def subscribe_data_change(self, node, **kwargs):
        self.calls.append((node, kwargs))
        return len(self.calls)


class FakeClient:
    def __init__(self, url):
        self.url = url
        self.connected = False
        self.session_timeout = 3600000

    async def connect(self):
        self.connected = True
        self.session_timeout = 600000

    async def disconnect(self):
        self.connected = False

    async def get_namespace_array(self):
        return ["http://opcfoundation.org/UA/"]

    def get_node(self, node_id):
        return FakeNode(node_id)

    async def create_subscription(self, period_ms, handler):
        return FakeSubscription()


class FakeClientFastSession(FakeClient):
    """Grants a tiny session timeout on connect so the renewal loop fires
    quickly — client.py floors the renewal interval at 1.0s regardless, so
    this just needs to be small enough to hit that floor."""

    async def connect(self):
        self.connected = True
        self.session_timeout = 50  # ms


def _factory(url):
    return FakeClient(url)


def _fast_session_factory(url):
    return FakeClientFastSession(url)


def _server():
    return ServerMapping(name="p1", endpoint_url="opc.tcp://p1/", subscriptions=[SubscriptionMapping(node="ns=2;s=A", measurement="a")])


def _wired_worker(server):
    worker = ServerWorker(server, None, None, MeasurementSink(), OpcuaMetrics())
    worker.connection = OpcUaConnection(server, client_factory=_factory)
    worker.subscriptions = SubscriptionManager(worker.connection, MeasurementSink())
    return worker


def test_build_security_config_none_for_open_server():
    assert build_security_config(_server()) is None


def test_build_security_config_set_for_secured_server():
    server = ServerMapping(name="p1", endpoint_url="opc.tcp://p1/", security_policy="Basic256Sha256",
                            security_mode="SignAndEncrypt", subscriptions=[SubscriptionMapping(node="ns=2;s=A", measurement="a")])
    sec = build_security_config(server)
    assert sec is not None
    assert sec.policy == "Basic256Sha256"
    assert sec.cert_path == Settings.SECURITY_CERT_PATH


def test_server_worker_connects_subscribes_and_shuts_down_gracefully():
    async def _run():
        worker = _wired_worker(_server())
        stop_event = asyncio.Event()

        async def stop_soon():
            await asyncio.sleep(0.15)
            stop_event.set()

        await asyncio.gather(worker.run(stop_event), stop_soon())
        return worker.connection.connected, worker.subscriptions.monitored_item_count

    connected, item_count = asyncio.run(_run())
    assert connected is False  # disconnected as part of graceful shutdown
    assert item_count == 1  # subscription was established before shutdown


def test_server_worker_reconnects_after_session_renewal_failure(monkeypatch):
    """asyncua isn't installed, so the session renewal loop's first attempt
    always fails (see client.py) and marks connected=False; this drives the
    worker's run loop back through reconnect_with_backoff. Shrinking the
    renewal margin and the poll interval keeps the test fast without
    changing the loop's actual logic."""
    monkeypatch.setattr(Settings, "CONNECTION_POLL_INTERVAL_S", 0.02)
    monkeypatch.setattr(Settings, "SESSION_RENEWAL_MARGIN_S", 0.0)
    monkeypatch.setattr(Settings, "RECONNECT_INITIAL_DELAY_S", 0.01)

    async def _run():
        worker = ServerWorker(_server(), None, None, MeasurementSink(), OpcuaMetrics())
        worker.connection = OpcUaConnection(_server(), client_factory=_fast_session_factory)
        worker.subscriptions = SubscriptionManager(worker.connection, MeasurementSink())
        stop_event = asyncio.Event()

        async def stop_after_a_reconnect():
            while worker.connection.reconnect_count < 2:
                await asyncio.sleep(0.02)
            stop_event.set()

        await asyncio.wait_for(asyncio.gather(worker.run(stop_event), stop_after_a_reconnect()), timeout=5)
        return worker.connection.reconnect_count

    reconnect_count = asyncio.run(_run())
    assert reconnect_count >= 2  # initial connect + at least one renewal-triggered reconnect
