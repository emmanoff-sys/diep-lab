"""OPC UA Phase 2 — subscription engine: browse (cached), monitored items,
deadband/queue configuration, and reconnect-driven monitored-item recovery.

Like client.py, asyncua is only imported inside the methods that need it.
`_build_filter()` is the one piece of the asyncua surface Phase 0's discovery
pass didn't separately exercise (deadband filter construction) — it fails
soft (logs and subscribes without a filter) rather than breaking the whole
subscription set over an optional refinement. See VALIDATION.md.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from .browse_cache import BrowseCache
from .client import OpcUaConnection
from .mapping import SubscriptionMapping
from .measurement import MeasurementSink, build_measurement

logger = logging.getLogger("diep-opcua.subscription")


class _DataChangeHandler:
    """Matches asyncua's SubHandler duck type:
    `datachange_notification(node, val, data)`."""

    def __init__(self, manager: "SubscriptionManager"):
        self._manager = manager

    def datachange_notification(self, node, val, data):
        self._manager._on_datachange(node, val, data)


class SubscriptionManager:
    def __init__(self, connection: OpcUaConnection, sink: MeasurementSink,
                 browse_cache: BrowseCache | None = None, metrics=None):
        self.connection = connection
        self.sink = sink
        self.browse_cache = browse_cache or BrowseCache()
        self.metrics = metrics
        self._subscription = None
        self._monitored_items: dict[str, tuple[object, SubscriptionMapping]] = {}

    @property
    def monitored_item_count(self) -> int:
        return len(self._monitored_items)

    async def browse(self, node_id: str) -> list:
        cached = self.browse_cache.get(node_id)
        if cached is not None:
            return cached
        start = time.monotonic()
        node = self.connection.client.get_node(node_id)
        children = await node.get_children()
        if self.metrics:
            self.metrics.browse_latency_seconds.labels(server=self.connection.server.name).observe(time.monotonic() - start)
        self.browse_cache.set(node_id, children)
        return children

    def _build_filter(self, item: SubscriptionMapping):
        if item.deadband_type == "none":
            return None
        try:
            from asyncua import ua
            deadband_type = {
                "absolute": ua.DeadbandType.Absolute,
                "percent": ua.DeadbandType.Percent,
            }[item.deadband_type]
            return ua.DataChangeFilter(
                Trigger=ua.DataChangeTrigger.StatusValue,
                DeadbandType=deadband_type,
                DeadbandValue=item.deadband_value,
            )
        except Exception as exc:  # noqa: BLE001 — deadband is an optimization, not a correctness requirement
            logger.warning(
                "%s: could not build deadband filter for %s (%s) — subscribing without it",
                self.connection.server.name, item.node, exc,
            )
            return None

    async def subscribe_all(self) -> None:
        start = time.monotonic()
        handler = _DataChangeHandler(self)
        period_ms = min((item.sampling_interval_ms for item in self.connection.server.subscriptions), default=1000.0)
        self._subscription = await self.connection.client.create_subscription(period_ms, handler)
        for item in self.connection.server.subscriptions:
            await self._subscribe_one(item)
        if self.metrics:
            self.metrics.subscription_latency_seconds.labels(server=self.connection.server.name).observe(time.monotonic() - start)
            self.metrics.monitored_items.labels(server=self.connection.server.name).set(len(self._monitored_items))

    async def _subscribe_one(self, item: SubscriptionMapping) -> None:
        node_id = self.connection.resolve_node_id(item.node)
        node = self.connection.client.get_node(node_id)
        data_filter = self._build_filter(item)
        kwargs = {"queuesize": item.queue_size, "sampling_interval": item.sampling_interval_ms}
        if data_filter is not None:
            kwargs["filter"] = data_filter
        handle = await self._subscription.subscribe_data_change(node, **kwargs)
        self._monitored_items[node_id] = (handle, item)
        logger.info("%s: subscribed %s -> %s", self.connection.server.name, node_id, item.measurement)

    def _on_datachange(self, node, val, data) -> None:
        node_id = node.nodeid.to_string() if hasattr(node, "nodeid") else str(node)
        entry = self._monitored_items.get(node_id)
        item = entry[1] if entry else None
        measurement_name = item.measurement if item else node_id

        status_code = "Good"
        source_ts = server_ts = None
        try:
            mv = data.monitored_item.Value
            sc = getattr(mv, "StatusCode", None)
            if sc is not None:
                status_code = "Good" if hasattr(sc, "is_good") and sc.is_good() else str(sc)
            source_ts = getattr(mv, "SourceTimestamp", None)
            server_ts = getattr(mv, "ServerTimestamp", None)
        except AttributeError:
            pass

        m = build_measurement(
            server_name=self.connection.server.name,
            node_id=node_id,
            measurement_name=measurement_name,
            value=val,
            data_type=type(val).__name__,
            status_code=status_code,
            source_timestamp=source_ts,
            server_timestamp=server_ts,
        )
        self.sink.emit(m)
        self._observe_publish_latency(m)

    def _observe_publish_latency(self, m) -> None:
        if not (self.metrics and m.source_timestamp and m.received_at):
            return
        try:
            src = datetime.fromisoformat(m.source_timestamp.replace("Z", "+00:00"))
            recv = datetime.fromisoformat(m.received_at.replace("Z", "+00:00"))
        except ValueError:
            return
        self.metrics.publish_latency_seconds.labels(server=self.connection.server.name).observe(
            max((recv - src).total_seconds(), 0.0)
        )

    async def recover_monitored_items(self) -> None:
        """Re-creates the subscription and every monitored item from the
        source-of-truth mapping (`connection.server.subscriptions`), not from
        stale handles — monitored items/subscriptions do not survive a
        session loss, so "recovery" means resubscribing from configuration,
        not restoring an old handle."""
        self._monitored_items.clear()
        self._subscription = None
        self.browse_cache.invalidate()
        await self.subscribe_all()
