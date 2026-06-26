"""CIM Prometheus metrics -- lazy `prometheus_client` import (same pattern
as services/opcua/metrics.py and services/mdm/metrics.py) so this module
stays importable without it; falls back to no-ops rather than crashing the
service over an observability dependency.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("diep-cim.metrics")


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


class CimMetrics:
    def __init__(self):
        try:
            from prometheus_client import Counter, Histogram
        except ImportError:
            logger.warning("prometheus_client not installed — metrics are no-ops")
            self.requests_total = _NoOpMetric()
            self.mapping_errors_total = _NoOpMetric()
            self.request_latency_seconds = _NoOpMetric()
            return

        self.requests_total = Counter(
            "cim_requests_total", "CIM REST API requests served", ["route", "status"],
        )
        self.mapping_errors_total = Counter(
            "cim_mapping_errors_total", "Errors mapping a DB row to a CIM object", ["object_type", "reason"],
        )
        self.request_latency_seconds = Histogram(
            "cim_request_latency_seconds", "CIM REST API request latency", ["route"],
        )
