"""OPC UA connector Prometheus metrics — lazy `prometheus_client` import
(same pattern as services/mdm/metrics.py) so this module stays importable
without it; falls back to no-ops rather than crashing the service over an
observability dependency.

`opcua_publish_latency_seconds` measures `received_at - source_timestamp`
per DataChange notification — i.e. how stale a value is by the time the
connector sees it (server-reported source timestamp to local receipt). This
is the OPC UA protocol-level "Publish" service path (the client polling the
server for queued subscription notifications) — unrelated to, and not to be
confused with, the MQTT/Kafka publishing this sprint explicitly excludes.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("diep-opcua.metrics")


class _NoOpMetric:
    def labels(self, *args, **kwargs):
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def set(self, value: float) -> None:
        pass

    def set_function(self, fn) -> None:
        pass


class OpcuaMetrics:
    def __init__(self):
        try:
            from prometheus_client import Counter, Gauge, Histogram
        except ImportError:
            logger.warning("prometheus_client not installed — metrics are no-ops")
            self.active_sessions = _NoOpMetric()
            self.reconnect_total = _NoOpMetric()
            self.monitored_items = _NoOpMetric()
            self.browse_latency_seconds = _NoOpMetric()
            self.subscription_latency_seconds = _NoOpMetric()
            self.publish_latency_seconds = _NoOpMetric()
            self.certificate_expiry_seconds = _NoOpMetric()
            self.connection_uptime_seconds = _NoOpMetric()
            return

        self.active_sessions = Gauge(
            "opcua_active_sessions", "1 if the connector currently holds an active session, else 0", ["server"],
        )
        self.reconnect_total = Counter(
            "opcua_reconnect_total", "Successful reconnects (session re-established after a disconnect)", ["server"],
        )
        self.monitored_items = Gauge(
            "opcua_monitored_items", "Currently active monitored items", ["server"],
        )
        self.browse_latency_seconds = Histogram(
            "opcua_browse_latency_seconds", "Latency of a single Browse service call", ["server"],
        )
        self.subscription_latency_seconds = Histogram(
            "opcua_subscription_latency_seconds", "Time to create a subscription and all its monitored items", ["server"],
        )
        self.publish_latency_seconds = Histogram(
            "opcua_publish_latency_seconds",
            "Per-DataChange staleness: local receipt time minus the server-reported source timestamp",
            ["server"],
        )
        self.certificate_expiry_seconds = Gauge(
            "opcua_certificate_expiry_seconds", "Seconds until the connector's own client certificate expires",
        )
        self.connection_uptime_seconds = Gauge(
            "opcua_connection_uptime_seconds", "Seconds since the current session was established (0 if disconnected)", ["server"],
        )
