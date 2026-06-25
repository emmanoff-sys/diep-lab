"""Tests for services/opcua/subscription.py using a fake asyncua-shaped
client/subscription/node (asyncua is not installed in this dev environment —
see VALIDATION.md). These exercise SubscriptionManager's own orchestration:
monitored-item bookkeeping, browse caching, deadband fallback behavior, and
DataChange -> InternalMeasurement construction."""
import asyncio
from datetime import datetime, timezone

from services.opcua.mapping import ServerMapping, SubscriptionMapping
from services.opcua.measurement import MeasurementSink
from services.opcua.metrics import OpcuaMetrics
from services.opcua.subscription import SubscriptionManager, _DataChangeHandler


class FakeNodeId:
    def __init__(self, s):
        self._s = s

    def to_string(self):
        return self._s


class FakeNode:
    def __init__(self, node_id):
        self.nodeid = FakeNodeId(node_id)
        self._node_id = node_id

    async def get_children(self):
        return [f"{self._node_id}/child"]


class FakeSubscription:
    def __init__(self):
        self.calls = []

    async def subscribe_data_change(self, node, **kwargs):
        self.calls.append((node, kwargs))
        return len(self.calls)


class FakeClient:
    def __init__(self):
        self.created_subscriptions = []

    def get_node(self, node_id):
        return FakeNode(node_id)

    async def create_subscription(self, period_ms, handler):
        sub = FakeSubscription()
        self.created_subscriptions.append((period_ms, sub, handler))
        return sub


class FakeConnection:
    def __init__(self, server):
        self.server = server
        self.client = FakeClient()

    def resolve_node_id(self, raw):
        return raw  # namespace resolution is tested separately, in test_opcua_client.py


class FakeStatusCode:
    def __init__(self, good=True, name="Good"):
        self._good = good
        self._name = name

    def is_good(self):
        return self._good

    def __str__(self):
        return self._name


class FakeDataValue:
    def __init__(self, status_code, source_ts, server_ts):
        self.StatusCode = status_code
        self.SourceTimestamp = source_ts
        self.ServerTimestamp = server_ts


class FakeMonitoredItemNotif:
    def __init__(self, value):
        self.Value = value


class FakeDataChangeNotif:
    def __init__(self, monitored_item):
        self.monitored_item = monitored_item


def _server_with_subs(subs):
    return ServerMapping(name="p1", endpoint_url="opc.tcp://p1/", subscriptions=subs)


def test_subscribe_all_creates_monitored_items_for_each_subscription():
    subs = [
        SubscriptionMapping(node="ns=2;s=A", measurement="a", sampling_interval_ms=500),
        SubscriptionMapping(node="ns=2;s=B", measurement="b", sampling_interval_ms=1000, queue_size=5),
    ]
    conn = FakeConnection(_server_with_subs(subs))
    mgr = SubscriptionManager(conn, MeasurementSink())
    asyncio.run(mgr.subscribe_all())

    assert mgr.monitored_item_count == 2
    assert "ns=2;s=A" in mgr._monitored_items
    period_ms, sub, _handler = conn.client.created_subscriptions[0]
    assert period_ms == 500  # min of the two sampling intervals
    assert len(sub.calls) == 2
    _, kwargs_b = sub.calls[1]
    assert kwargs_b["queuesize"] == 5


def test_deadband_falls_back_gracefully_without_asyncua():
    subs = [SubscriptionMapping(node="ns=2;s=A", measurement="a", deadband_type="absolute", deadband_value=0.5)]
    conn = FakeConnection(_server_with_subs(subs))
    mgr = SubscriptionManager(conn, MeasurementSink())
    asyncio.run(mgr.subscribe_all())

    _, kwargs = conn.client.created_subscriptions[0][1].calls[0]
    assert "filter" not in kwargs  # asyncua not installed here -> _build_filter logs and returns None


def test_recover_monitored_items_rebuilds_from_mapping():
    subs = [SubscriptionMapping(node="ns=2;s=A", measurement="a")]
    conn = FakeConnection(_server_with_subs(subs))
    mgr = SubscriptionManager(conn, MeasurementSink())
    asyncio.run(mgr.subscribe_all())
    asyncio.run(mgr.recover_monitored_items())

    assert mgr.monitored_item_count == 1
    assert len(conn.client.created_subscriptions) == 2  # subscribed once, then again on recovery


def test_browse_uses_cache_on_second_call():
    conn = FakeConnection(_server_with_subs([SubscriptionMapping(node="ns=2;s=A", measurement="a")]))
    mgr = SubscriptionManager(conn, MeasurementSink())

    children1 = asyncio.run(mgr.browse("ns=2;s=Folder"))
    calls = {"n": 0}
    orig_get_node = conn.client.get_node

    def counting_get_node(node_id):
        calls["n"] += 1
        return orig_get_node(node_id)

    conn.client.get_node = counting_get_node
    children2 = asyncio.run(mgr.browse("ns=2;s=Folder"))

    assert children2 == children1
    assert calls["n"] == 0  # cache hit — get_node was not called the second time


def test_on_datachange_builds_measurement_and_emits():
    conn = FakeConnection(_server_with_subs([SubscriptionMapping(node="ns=2;s=A", measurement="battery_soc")]))
    sink = MeasurementSink()
    mgr = SubscriptionManager(conn, sink)
    asyncio.run(mgr.subscribe_all())

    now = datetime.now(timezone.utc)
    data = FakeDataChangeNotif(FakeMonitoredItemNotif(FakeDataValue(FakeStatusCode(good=True), now, now)))
    mgr._on_datachange(FakeNode("ns=2;s=A"), 87.5, data)

    latest = sink.latest()
    assert latest["p1/battery_soc"]["value"] == 87.5
    assert latest["p1/battery_soc"]["valid"] is True


def test_on_datachange_unknown_node_falls_back_to_node_id_as_measurement_name():
    conn = FakeConnection(_server_with_subs([SubscriptionMapping(node="ns=2;s=A", measurement="a")]))
    sink = MeasurementSink()
    mgr = SubscriptionManager(conn, sink)

    data = FakeDataChangeNotif(FakeMonitoredItemNotif(FakeDataValue(FakeStatusCode(good=True), None, None)))
    mgr._on_datachange(FakeNode("ns=2;s=UNMAPPED"), 1.0, data)

    assert "p1/ns=2;s=UNMAPPED" in sink.latest()


def test_on_datachange_bad_status_marks_measurement_invalid():
    conn = FakeConnection(_server_with_subs([SubscriptionMapping(node="ns=2;s=A", measurement="a")]))
    sink = MeasurementSink()
    mgr = SubscriptionManager(conn, sink)
    asyncio.run(mgr.subscribe_all())

    data = FakeDataChangeNotif(FakeMonitoredItemNotif(FakeDataValue(FakeStatusCode(good=False, name="Bad_NodeIdUnknown"), None, None)))
    mgr._on_datachange(FakeNode("ns=2;s=A"), None, data)

    assert sink.latest()["p1/a"]["valid"] is False


def test_on_datachange_records_publish_latency_metric_without_crashing():
    conn = FakeConnection(_server_with_subs([SubscriptionMapping(node="ns=2;s=A", measurement="a")]))
    metrics = OpcuaMetrics()  # NoOp fallback, since prometheus_client is not installed here
    mgr = SubscriptionManager(conn, MeasurementSink(), metrics=metrics)

    now = datetime.now(timezone.utc)
    data = FakeDataChangeNotif(FakeMonitoredItemNotif(FakeDataValue(FakeStatusCode(good=True), now, now)))
    mgr._on_datachange(FakeNode("ns=2;s=A"), 1.0, data)  # must not raise


def test_datachange_handler_delegates_to_manager():
    conn = FakeConnection(_server_with_subs([SubscriptionMapping(node="ns=2;s=A", measurement="a")]))
    sink = MeasurementSink()
    mgr = SubscriptionManager(conn, sink)
    asyncio.run(mgr.subscribe_all())  # populates _monitored_items so the node id maps to "a", not its raw node id
    handler = _DataChangeHandler(mgr)

    data = FakeDataChangeNotif(FakeMonitoredItemNotif(FakeDataValue(FakeStatusCode(good=True), None, None)))
    handler.datachange_notification(FakeNode("ns=2;s=A"), 5.0, data)

    assert sink.latest()["p1/a"]["value"] == 5.0
