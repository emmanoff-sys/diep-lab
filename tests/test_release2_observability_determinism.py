from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request

from services.mdm.health import start_health_server as start_mdm_health_server
from services.mdm.metrics import MdmMetrics
from services.mdm.metrics import _NoOpMetric as MdmNoOpMetric
from services.opcua.metrics import OpcuaMetrics
from services.opcua.metrics import _NoOpMetric as OpcuaNoOpMetric


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_prometheus_profile_absent_forces_mdm_noop_even_when_dependency_exists(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_PROFILE", "absent")

    metrics = MdmMetrics()

    assert isinstance(metrics.measurements_processed_total, MdmNoOpMetric)
    metrics.measurements_processed_total.inc()
    metrics.processing_latency_seconds.observe(0.01)


def test_prometheus_profile_absent_forces_opcua_noop_even_when_dependency_exists(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_PROFILE", "absent")

    metrics = OpcuaMetrics()

    assert isinstance(metrics.active_sessions, OpcuaNoOpMetric)
    metrics.active_sessions.labels(server="p1").set(1)
    metrics.publish_latency_seconds.labels(server="p1").observe(0.01)


def test_isolated_registry_allows_repeated_mdm_metric_construction(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_PROFILE", "isolated-registry")

    first = MdmMetrics()
    second = MdmMetrics()

    first.measurements_processed_total.inc()
    second.measurements_processed_total.inc()


def test_isolated_registry_allows_repeated_opcua_metric_construction(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_PROFILE", "isolated-registry")

    first = OpcuaMetrics()
    second = OpcuaMetrics()

    first.active_sessions.labels(server="p1").set(1)
    second.active_sessions.labels(server="p1").set(1)


def test_prometheus_profile_absent_controls_mdm_metrics_endpoint(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_PROFILE", "absent")
    server = start_mdm_health_server(free_port())
    try:
        time.sleep(0.05)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/metrics", timeout=2)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = True
            assert exc.code == 503
        assert raised
    finally:
        server.shutdown()
