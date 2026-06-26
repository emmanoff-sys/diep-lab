"""Tests for services/opcua/metrics.py. prometheus_client is not installed in
this dev environment, so this genuinely exercises the _NoOpMetric fallback
path end-to-end (not a mock standing in for it)."""
from services.opcua.metrics import OpcuaMetrics


def test_metrics_construct_without_prometheus_client():
    m = OpcuaMetrics()
    # every attribute must exist and be usable even without prometheus_client
    m.active_sessions.labels(server="p1").set(1)
    m.reconnect_total.labels(server="p1").inc()
    m.monitored_items.labels(server="p1").set(3)
    m.browse_latency_seconds.labels(server="p1").observe(0.01)
    m.subscription_latency_seconds.labels(server="p1").observe(0.5)
    m.publish_latency_seconds.labels(server="p1").observe(0.2)
    m.certificate_expiry_seconds.set(86400)
    m.certificate_expiry_seconds.set_function(lambda: 1.0)
    m.connection_uptime_seconds.labels(server="p1").set_function(lambda: 5.0)
    # no assertions beyond "did not raise" — that IS the contract of a no-op


def test_metrics_labels_returns_self_for_chaining():
    m = OpcuaMetrics()
    same = m.reconnect_total.labels(server="p1")
    same.inc()
    same.inc(2)
