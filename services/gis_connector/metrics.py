"""OA-097 — GIS connector Prometheus metrics.

Lazy prometheus_client import with _NoOpMetric fallback — importable and
usable without prometheus_client installed.

GIS processes topology batches rather than individual events; metrics
reflect batch-level outcomes and feature-level translation statistics.

Metric prefix: re_os_gis_connector_*
"""

from __future__ import annotations

import logging

logger = logging.getLogger("re-os.gis-connector.metrics")


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


class GISConnectorMetrics:
    """Prometheus metrics holder for the GIS topology adapter.

    Instantiate once per process.
    """

    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Gauge
        except ImportError:
            logger.warning("prometheus_client not installed — GIS connector metrics are no-ops")
            self._init_noops()
            return

        self.batches_processed_total = Counter(
            "re_os_gis_connector_batches_processed_total",
            "GIS connector topology batches successfully translated",
            ["connector_id"],
        )
        self.batches_dead_lettered_total = Counter(
            "re_os_gis_connector_batches_dead_lettered_total",
            "GIS connector topology batches written to dead-letter queue (zero output)",
            ["connector_id"],
        )
        self.features_translated_total = Counter(
            "re_os_gis_connector_features_translated_total",
            "GIS connector features successfully translated to canonical topology",
            ["connector_id", "feature_type"],
        )
        self.features_rejected_total = Counter(
            "re_os_gis_connector_features_rejected_total",
            "GIS connector features rejected during translation",
            ["connector_id"],
        )
        self.reconciliation_items_total = Counter(
            "re_os_gis_connector_reconciliation_items_total",
            "GIS connector reconciliation report items by kind",
            ["connector_id", "kind"],
        )
        self.buffer_overflow_total = Counter(
            "re_os_gis_connector_buffer_overflow_total",
            "GIS connector topology buffer overflow evictions (oldest batch dropped)",
            ["connector_id"],
        )
        self.dlq_overflow_total = Counter(
            "re_os_gis_connector_dlq_overflow_total",
            "GIS connector dead-letter queue overflow evictions",
            ["connector_id"],
        )
        self.connector_healthy = Gauge(
            "re_os_gis_connector_healthy",
            "1 if the GIS connector is healthy (status=active), 0 otherwise",
            ["connector_id"],
        )

    def _init_noops(self) -> None:
        self.batches_processed_total = _NoOpMetric()
        self.batches_dead_lettered_total = _NoOpMetric()
        self.features_translated_total = _NoOpMetric()
        self.features_rejected_total = _NoOpMetric()
        self.reconciliation_items_total = _NoOpMetric()
        self.buffer_overflow_total = _NoOpMetric()
        self.dlq_overflow_total = _NoOpMetric()
        self.connector_healthy = _NoOpMetric()
