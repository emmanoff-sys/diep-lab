"""Ingestor Prometheus metrics — lazy `prometheus_client` import (same
pattern as services/opcua/metrics.py and services/mdm/metrics.py) so this
module stays importable without it; falls back to no-ops rather than
crashing the service over an observability dependency.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("diep-ingestor.metrics")


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


class IngestorMetrics:
    def __init__(self):
        try:
            from prometheus_client import Counter, Gauge, Histogram
        except ImportError:
            logger.warning("prometheus_client not installed — metrics are no-ops")
            self.messages_received_total = _NoOpMetric()
            self.messages_dropped_total = _NoOpMetric()
            self.messages_rejected_total = _NoOpMetric()
            self.messages_persisted_total = _NoOpMetric()
            self.queue_depth = _NoOpMetric()
            self.post_latency_seconds = _NoOpMetric()
            return

        self.messages_received_total = Counter(
            "ingestor_messages_received_total", "Telemetry messages received off MQTT",
        )
        self.messages_dropped_total = Counter(
            "ingestor_messages_dropped_total",
            "Messages dropped before validation (e.g. queue full under sustained overload)",
            ["reason"],
        )
        self.messages_rejected_total = Counter(
            "ingestor_messages_rejected_total",
            "Messages/measurements rejected during validation (envelope-level or per-field)",
            ["reason"],
        )
        self.messages_persisted_total = Counter(
            "ingestor_messages_persisted_total", "POST /telemetry outcomes", ["status"],
        )
        self.queue_depth = Gauge(
            "ingestor_queue_depth", "Current depth of the receive->worker bounded queue",
        )
        self.post_latency_seconds = Histogram(
            "ingestor_post_latency_seconds", "Latency of a single POST /telemetry call",
        )
