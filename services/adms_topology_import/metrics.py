"""Prometheus metrics for the ADMS topology import foundation."""

from __future__ import annotations

import logging

logger = logging.getLogger("diep-adms-topology-import.metrics")


class _NoOpMetric:
    def labels(self, *args, **kwargs):
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass


class AdmsImportMetrics:
    """Metrics holder with a no-op fallback for minimal local environments."""

    def __init__(self, *, enabled: bool = True):
        if not enabled:
            self.imports_total = _NoOpMetric()
            self.import_latency_seconds = _NoOpMetric()
            self.lifecycle_events_total = _NoOpMetric()
            self.validation_failures_total = _NoOpMetric()
            self.staged_imports_gauge = _NoOpMetric()
            return

        try:
            from prometheus_client import Counter, Gauge, Histogram
        except ImportError:
            logger.warning("prometheus_client not installed - ADMS import metrics are no-ops")
            self.imports_total = _NoOpMetric()
            self.import_latency_seconds = _NoOpMetric()
            self.lifecycle_events_total = _NoOpMetric()
            self.validation_failures_total = _NoOpMetric()
            self.staged_imports_gauge = _NoOpMetric()
            return

        self.imports_total = Counter(
            "adms_topology_imports_total",
            "ADMS topology import attempts observed by status",
            ["status"],
        )
        self.import_latency_seconds = Histogram(
            "adms_topology_import_latency_seconds",
            "ADMS topology import processing latency",
            ["stage"],
        )
        self.lifecycle_events_total = Counter(
            "adms_topology_import_lifecycle_events_total",
            "ADMS topology import lifecycle events observed",
            ["status", "outcome"],
        )
        self.validation_failures_total = Counter(
            "adms_topology_import_validation_failures_total",
            "ADMS topology import validation failures observed",
            ["reason_code"],
        )
        self.staged_imports_gauge = Gauge(
            "adms_topology_import_staged_imports",
            "Current ADMS topology imports in a staged lifecycle state",
            ["status"],
        )
