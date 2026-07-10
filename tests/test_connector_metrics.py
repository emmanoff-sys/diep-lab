"""OA-097 — Connector Prometheus metrics tests (WP-026).

Verifies that SCADAConnectorMetrics, GISConnectorMetrics, and
AMIConnectorMetrics all initialise without error and expose the correct
instrument names, with no-op fallback when prometheus_client is blocked.

Follows the established pattern from test_cim_metrics.py — each class is
instantiated once at module level to avoid double-registration with
Prometheus's default registry.
"""

from __future__ import annotations

import builtins
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ami_connector.metrics import AMIConnectorMetrics
from services.ami_connector.metrics import _NoOpMetric as AmiNoOp  # noqa: E402
from services.gis_connector.metrics import GISConnectorMetrics
from services.gis_connector.metrics import _NoOpMetric as GisNoOp  # noqa: E402
from services.scada_connector.metrics import (
    SCADAConnectorMetrics,
)
from services.scada_connector.metrics import _NoOpMetric as ScadaNoOp  # noqa: E402

# Module-level singletons to avoid Prometheus double-registration.
_SCADA_METRICS = SCADAConnectorMetrics()
_GIS_METRICS = GISConnectorMetrics()
_AMI_METRICS = AMIConnectorMetrics()


# --- SCADAConnectorMetrics -----------------------------------------------------


def test_scada_metrics_has_all_instruments():
    m = _SCADA_METRICS
    assert hasattr(m, "events_processed_total")
    assert hasattr(m, "events_rejected_total")
    assert hasattr(m, "events_dead_lettered_total")
    assert hasattr(m, "buffer_overflow_total")
    assert hasattr(m, "dlq_overflow_total")
    assert hasattr(m, "buffer_size")
    assert hasattr(m, "dlq_size")
    assert hasattr(m, "connector_healthy")


def test_scada_metrics_instruments_are_callable():
    m = _SCADA_METRICS
    m.events_processed_total.labels(connector_id="c1", event_type="breaker_operation").inc()
    m.events_rejected_total.labels(connector_id="c1", reason="stale").inc()
    m.events_dead_lettered_total.labels(connector_id="c1").inc()
    m.buffer_overflow_total.labels(connector_id="c1").inc()
    m.dlq_overflow_total.labels(connector_id="c1").inc()
    m.buffer_size.labels(connector_id="c1").set(10)
    m.dlq_size.labels(connector_id="c1").set(0)
    m.connector_healthy.labels(connector_id="c1").set(1)


def test_scada_metrics_noop_when_prometheus_blocked():
    real_import = builtins.__import__

    def blocking(name, *args, **kwargs):
        if name == "prometheus_client":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = blocking
    try:
        m = SCADAConnectorMetrics()
    finally:
        builtins.__import__ = real_import

    assert isinstance(m.events_processed_total, ScadaNoOp)
    assert isinstance(m.connector_healthy, ScadaNoOp)
    m.connector_healthy.labels(connector_id="x").set(1)  # must not raise


# --- GISConnectorMetrics -------------------------------------------------------


def test_gis_metrics_has_all_instruments():
    m = _GIS_METRICS
    assert hasattr(m, "batches_processed_total")
    assert hasattr(m, "batches_dead_lettered_total")
    assert hasattr(m, "features_translated_total")
    assert hasattr(m, "features_rejected_total")
    assert hasattr(m, "reconciliation_items_total")
    assert hasattr(m, "buffer_overflow_total")
    assert hasattr(m, "dlq_overflow_total")
    assert hasattr(m, "connector_healthy")


def test_gis_metrics_instruments_are_callable():
    m = _GIS_METRICS
    m.batches_processed_total.labels(connector_id="g1").inc()
    m.batches_dead_lettered_total.labels(connector_id="g1").inc()
    m.features_translated_total.labels(connector_id="g1", feature_type="node").inc(7)
    m.features_rejected_total.labels(connector_id="g1").inc()
    m.reconciliation_items_total.labels(connector_id="g1", kind="new_asset").inc(2)
    m.buffer_overflow_total.labels(connector_id="g1").inc()
    m.dlq_overflow_total.labels(connector_id="g1").inc()
    m.connector_healthy.labels(connector_id="g1").set(1)


def test_gis_metrics_noop_when_prometheus_blocked():
    real_import = builtins.__import__

    def blocking(name, *args, **kwargs):
        if name == "prometheus_client":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = blocking
    try:
        m = GISConnectorMetrics()
    finally:
        builtins.__import__ = real_import

    assert isinstance(m.batches_processed_total, GisNoOp)
    m.batches_processed_total.labels(connector_id="x").inc()  # must not raise


# --- AMIConnectorMetrics -------------------------------------------------------


def test_ami_metrics_has_all_instruments():
    m = _AMI_METRICS
    assert hasattr(m, "events_processed_total")
    assert hasattr(m, "events_rejected_total")
    assert hasattr(m, "events_dead_lettered_total")
    assert hasattr(m, "buffer_overflow_total")
    assert hasattr(m, "dlq_overflow_total")
    assert hasattr(m, "buffer_size")
    assert hasattr(m, "dlq_size")
    assert hasattr(m, "connector_healthy")


def test_ami_metrics_instruments_are_callable():
    m = _AMI_METRICS
    m.events_processed_total.labels(connector_id="a1", message_type="last_gasp").inc()
    m.events_rejected_total.labels(connector_id="a1", reason="stale").inc()
    m.events_dead_lettered_total.labels(connector_id="a1").inc()
    m.buffer_overflow_total.labels(connector_id="a1").inc()
    m.dlq_overflow_total.labels(connector_id="a1").inc()
    m.buffer_size.labels(connector_id="a1").set(5)
    m.dlq_size.labels(connector_id="a1").set(0)
    m.connector_healthy.labels(connector_id="a1").set(1)


def test_ami_metrics_noop_when_prometheus_blocked():
    real_import = builtins.__import__

    def blocking(name, *args, **kwargs):
        if name == "prometheus_client":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = blocking
    try:
        m = AMIConnectorMetrics()
    finally:
        builtins.__import__ = real_import

    assert isinstance(m.events_processed_total, AmiNoOp)
    m.events_processed_total.labels(connector_id="x", message_type="last_gasp").inc()
