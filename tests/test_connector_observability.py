"""OA-097 — Connector health HTTP server tests (WP-026).

Verifies that ConnectorHealthServer correctly exposes /health, /ready,
/live, and /metrics endpoints. Tests use real stdlib HTTP on a loopback
port — no mocking of the server itself.

Follows the established pattern from test_opcua_health.py.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from services.scada_connector import (  # noqa: E402
    ConnectorConfig,
    ConnectorHealthServer,
    ConnectorLifecycle,
    start_connector_health_server,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_lifecycle(connector_id: str = "test-scada-01") -> ConnectorLifecycle:
    config = ConnectorConfig(connector_id=connector_id, actor="test-actor")
    return ConnectorLifecycle(config)


# --- /health -------------------------------------------------------------------


def test_health_endpoint_returns_200_and_down_when_idle():
    lifecycle = _make_lifecycle()
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            body = json.loads(resp.read())
        assert resp.status == 200
        assert body["connector_id"] == "test-scada-01"
        assert body["status"] == "DOWN"  # lifecycle is idle, not active
        assert body["healthy"] is False
    finally:
        server.stop()


def test_health_endpoint_returns_up_when_active():
    lifecycle = _make_lifecycle("test-scada-02")
    lifecycle.on_connect()  # transitions to active → healthy
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            body = json.loads(resp.read())
        assert body["status"] == "UP"
        assert body["healthy"] is True
        assert body["session_count"] == 1
    finally:
        server.stop()


def test_health_endpoint_reports_event_counts():
    lifecycle = _make_lifecycle("test-scada-03")
    lifecycle.on_connect()
    lifecycle.on_event_submitted()
    lifecycle.on_event_submitted()
    lifecycle.on_event_rejected("stale sequence")
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            body = json.loads(resp.read())
        assert body["events_submitted"] == 2
        assert body["events_rejected"] == 1
    finally:
        server.stop()


# --- /ready --------------------------------------------------------------------


def test_ready_returns_200_when_healthy():
    lifecycle = _make_lifecycle("test-scada-04")
    lifecycle.on_connect()
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=2) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
        assert body["ready"] is True
    finally:
        server.stop()


def test_ready_returns_503_when_idle():
    lifecycle = _make_lifecycle("test-scada-05")
    # Do NOT call on_connect() — lifecycle remains idle
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        raised = False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=2)
        except urllib.error.HTTPError as exc:
            raised = True
            assert exc.code == 503
            body = json.loads(exc.read())
            assert body["ready"] is False
        assert raised
    finally:
        server.stop()


# --- /live ---------------------------------------------------------------------


def test_live_always_returns_200():
    lifecycle = _make_lifecycle("test-scada-06")
    # Even with a degraded connector, /live must return 200
    lifecycle.on_degraded("transient network issue")
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/live", timeout=2) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
        assert body["live"] is True
    finally:
        server.stop()


# --- /metrics ------------------------------------------------------------------


def test_metrics_endpoint_503_without_prometheus_or_200_with_it():
    lifecycle = _make_lifecycle("test-scada-07")
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        from importlib.util import find_spec

        has_prometheus = find_spec("prometheus_client") is not None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2) as resp:
                assert has_prometheus, "expected 503 without prometheus_client"
                assert resp.status == 200
        except urllib.error.HTTPError as exc:
            assert not has_prometheus or exc.code == 503
    finally:
        server.stop()


# --- Unknown path --------------------------------------------------------------


def test_unknown_path_404():
    lifecycle = _make_lifecycle("test-scada-08")
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    try:
        time.sleep(0.05)
        raised = False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=2)
        except urllib.error.HTTPError as exc:
            raised = True
            assert exc.code == 404
        assert raised
    finally:
        server.stop()


# --- ConnectorHealthServer lifecycle -------------------------------------------


def test_health_server_start_and_stop():
    lifecycle = _make_lifecycle("test-scada-09")
    port = _free_port()
    srv = ConnectorHealthServer(lifecycle, port)
    srv.start()
    time.sleep(0.05)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/live", timeout=2) as resp:
        assert resp.status == 200
    srv.stop()


def test_health_server_double_start_raises():
    import pytest

    lifecycle = _make_lifecycle("test-scada-10")
    port = _free_port()
    srv = ConnectorHealthServer(lifecycle, port)
    srv.start()
    try:
        with pytest.raises(RuntimeError):
            srv.start()
    finally:
        srv.stop()


# --- start_connector_health_server convenience ---------------------------------


def test_start_connector_health_server_convenience():
    lifecycle = _make_lifecycle("test-scada-11")
    port = _free_port()
    server = start_connector_health_server(lifecycle, port)
    assert isinstance(server, ConnectorHealthServer)
    time.sleep(0.05)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/live", timeout=2) as resp:
        assert resp.status == 200
    server.stop()
