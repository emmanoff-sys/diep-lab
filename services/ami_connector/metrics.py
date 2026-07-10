"""OA-097 — AMI connector Prometheus metrics.

Lazy prometheus_client import with _NoOpMetric fallback — importable and
usable without prometheus_client installed.

Metric prefix: re_os_ami_connector_*
"""

from __future__ import annotations

import logging

logger = logging.getLogger("re-os.ami-connector.metrics")


class _NoOpMetric:
    def labels(self, *args, **kwargs) -> _NoOpMetric:
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def set(self, value: float) -> None:
        pass

    def set_function(self, fn) -> None:
        pass


class AMIConnectorMetrics:
    """Prometheus metrics holder for the AMI metering connector.

    Instantiate once per process.
    """

    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Gauge
        except ImportError:
            logger.warning("prometheus_client not installed — AMI connector metrics are no-ops")
            self._init_noops()
            return

        self.events_processed_total = Counter(
            "re_os_ami_connector_events_processed_total",
            "AMI connector events successfully submitted to ingestion pipeline",
            ["connector_id", "message_type"],
        )
        self.events_rejected_total = Counter(
            "re_os_ami_connector_events_rejected_total",
            "AMI connector events rejected by the ingestion pipeline (non-duplicate)",
            ["connector_id", "reason"],
        )
        self.events_dead_lettered_total = Counter(
            "re_os_ami_connector_events_dead_lettered_total",
            "AMI connector events written to the dead-letter queue",
            ["connector_id"],
        )
        self.buffer_overflow_total = Counter(
            "re_os_ami_connector_buffer_overflow_total",
            "AMI connector event buffer overflow evictions (oldest message dropped)",
            ["connector_id"],
        )
        self.dlq_overflow_total = Counter(
            "re_os_ami_connector_dlq_overflow_total",
            "AMI connector dead-letter queue overflow evictions",
            ["connector_id"],
        )
        self.buffer_size = Gauge(
            "re_os_ami_connector_buffer_size",
            "Current number of messages in the AMI connector event buffer",
            ["connector_id"],
        )
        self.dlq_size = Gauge(
            "re_os_ami_connector_dlq_size",
            "Current number of records in the AMI connector dead-letter queue",
            ["connector_id"],
        )
        self.connector_healthy = Gauge(
            "re_os_ami_connector_healthy",
            "1 if the AMI connector is healthy (status=active), 0 otherwise",
            ["connector_id"],
        )

    def _init_noops(self) -> None:
        self.events_processed_total = _NoOpMetric()
        self.events_rejected_total = _NoOpMetric()
        self.events_dead_lettered_total = _NoOpMetric()
        self.buffer_overflow_total = _NoOpMetric()
        self.dlq_overflow_total = _NoOpMetric()
        self.buffer_size = _NoOpMetric()
        self.dlq_size = _NoOpMetric()
        self.connector_healthy = _NoOpMetric()
