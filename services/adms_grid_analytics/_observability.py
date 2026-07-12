"""Shared analytics observability utilities (OA-137 / OA-138).

Structured logging
------------------
All five analytics service classes emit events under the ``diep.analytics``
logger namespace. Each log record uses Python's standard logging module with
structured key=value fields embedded in the message so any log aggregator can
parse them without a custom formatter.

Events emitted per service call:
  [service.start]    — method invoked; node/edge counts; contract version.
  [service.complete] — successful return; duration_ms.
  [service.failure]  — exception raised; exc_type; duration_ms.

Fields present on every record:
  service, method, status (complete/failure only), duration_ms
  (complete/failure only), contract_version.

Optional field (forwarded from ``options.get("correlation_id")`` when present):
  correlation_id.

No raw analytical data (node attrs, edge impedances, measurement values) is
logged. No credentials or secrets are included.

Prometheus metrics
------------------
``AnalyticsMetrics`` wraps prometheus_client counters/histograms. When the
library is not installed, every metric falls back to a ``_NoOpMetric`` stub
that accepts the same API and discards all data — the analytics services
remain fully operational and test-safe.

The module-level singleton ``_metrics`` is shared by all service instances.
Tests that need isolated metric state can construct a fresh ``AnalyticsMetrics``
and call the module-level helper functions with the ``metrics=`` keyword argument.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("diep.analytics")


class _NoOpMetric:
    def labels(self, *args, **kwargs):
        return self

    def inc(self, amount: float = 1.0) -> None:
        pass

    def observe(self, amount: float) -> None:
        pass

    def set(self, value: float) -> None:
        pass


class AnalyticsMetrics:
    """Prometheus metrics for the analytics service layer.

    Instantiate once at module level; pass as ``metrics=`` to the helper
    functions in tests that need isolated state.

    Metric label cardinality is bounded: ``service`` has 5 values, ``method``
    has ~12 values, ``status`` has 2 values.

    Parameters
    ----------
    registry:
        Optional prometheus_client ``CollectorRegistry``. Pass a fresh
        ``CollectorRegistry()`` in tests to avoid duplicate-registration
        errors when constructing multiple instances in the same process.
        Defaults to the global ``prometheus_client.REGISTRY``.
    """

    def __init__(self, registry=None) -> None:
        try:
            from prometheus_client import Counter, Histogram

            if registry is None:
                from prometheus_client import REGISTRY

                registry = REGISTRY
        except ImportError:
            logging.getLogger("diep.analytics.metrics").warning(
                "prometheus_client not installed — analytics metrics are no-ops"
            )
            self.requests_total = _NoOpMetric()
            self.request_duration_seconds = _NoOpMetric()
            self.convergence_failures_total = _NoOpMetric()
            self.topology_validation_failures_total = _NoOpMetric()
            self.boundary_validation_failures_total = _NoOpMetric()
            self.vvo_guard_rejections_total = _NoOpMetric()
            self.vvo_configurations_evaluated_total = _NoOpMetric()
            return

        self.requests_total = Counter(
            "analytics_requests_total",
            "Total analytics service requests by service, method, and outcome",
            ["service", "method", "status"],
            registry=registry,
        )
        self.request_duration_seconds = Histogram(
            "analytics_request_duration_seconds",
            "Wall-clock duration of analytics service calls",
            ["service", "method"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=registry,
        )
        self.convergence_failures_total = Counter(
            "analytics_convergence_failures_total",
            "State estimation or power flow convergence failures",
            ["service"],
            registry=registry,
        )
        self.topology_validation_failures_total = Counter(
            "analytics_topology_validation_failures_total",
            "Topology validation failures at the service boundary",
            ["service"],
            registry=registry,
        )
        self.boundary_validation_failures_total = Counter(
            "analytics_boundary_validation_failures_total",
            "Contract boundary validation failures at the service boundary",
            ["service"],
            registry=registry,
        )
        self.vvo_guard_rejections_total = Counter(
            "analytics_vvo_guard_rejections_total",
            "Volt/VAR device-count guard rejections (OA-139)",
            registry=registry,
        )
        self.vvo_configurations_evaluated_total = Counter(
            "analytics_vvo_configurations_evaluated_total",
            "Volt/VAR device configurations evaluated across all optimize() calls",
            registry=registry,
        )


_metrics = AnalyticsMetrics()


def record_start(
    service: str,
    method: str,
    *,
    node_count: int = 0,
    edge_count: int = 0,
    correlation_id: str | None = None,
) -> float:
    """Emit a service.start log record and return ``time.monotonic()`` as t0.

    Call at the top of each service method before the primary computation.
    Pass the returned t0 to ``record_complete`` or ``record_failure``.
    """
    from . import contracts

    fields = (
        f"service={service} method={method} "
        f"node_count={node_count} edge_count={edge_count} "
        f"contract_version={contracts.CONTRACT_VERSION}"
    )
    if correlation_id:
        fields += f" correlation_id={correlation_id}"
    logging.getLogger(f"diep.analytics.{service}").info("[service.start] %s", fields)
    return time.monotonic()


def record_complete(
    service: str,
    method: str,
    t0: float,
    *,
    extra: str = "",
    metrics: AnalyticsMetrics | None = None,
) -> None:
    """Emit a service.complete log record and update success metrics.

    ``extra`` is appended verbatim to the log fields and should be a
    space-separated list of ``key=value`` pairs with no secrets or raw data.
    """
    m = metrics if metrics is not None else _metrics
    duration_ms = round((time.monotonic() - t0) * 1000.0, 1)
    duration_s = duration_ms / 1000.0
    fields = f"service={service} method={method} status=success duration_ms={duration_ms}"
    if extra:
        fields += f" {extra}"
    logging.getLogger(f"diep.analytics.{service}").info("[service.complete] %s", fields)
    m.requests_total.labels(service=service, method=method, status="success").inc()
    m.request_duration_seconds.labels(service=service, method=method).observe(duration_s)


def record_failure(
    service: str,
    method: str,
    t0: float,
    exc: BaseException,
    *,
    metrics: AnalyticsMetrics | None = None,
) -> None:
    """Emit a service.failure log record and update failure metrics.

    Call inside an ``except`` block before re-raising. Does not suppress the
    exception.
    """
    m = metrics if metrics is not None else _metrics
    duration_ms = round((time.monotonic() - t0) * 1000.0, 1)
    duration_s = duration_ms / 1000.0
    fields = (
        f"service={service} method={method} status=failure "
        f"duration_ms={duration_ms} exc_type={type(exc).__name__}"
    )
    logging.getLogger(f"diep.analytics.{service}").warning("[service.failure] %s", fields)
    m.requests_total.labels(service=service, method=method, status="failure").inc()
    m.request_duration_seconds.labels(service=service, method=method).observe(duration_s)


def record_pf_complete(
    service: str,
    method: str,
    t0: float,
    pf_result: dict,
    *,
    metrics: AnalyticsMetrics | None = None,
) -> None:
    """Emit service.complete and update quality metrics for a power flow result.

    Checks ``pf_result`` for convergence failure and increments
    ``convergence_failures_total`` when not converged. Isolates all
    power-flow-result field reads in this module so the service layer
    remains free of engine-internal field references.
    """
    m = metrics if metrics is not None else _metrics
    n_viol = pf_result.get("violation_count", 0)
    pf_ok = bool(pf_result.get("converged", True))
    if not pf_ok:
        m.convergence_failures_total.labels(service=service).inc()
    record_complete(
        service,
        method,
        t0,
        extra=f"pf_ok={pf_ok} violation_count={n_viol}",
        metrics=m,
    )
