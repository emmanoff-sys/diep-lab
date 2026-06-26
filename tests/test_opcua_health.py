"""Tests for services/opcua/health.py — real stdlib HTTP server on a loopback
port, real socket I/O (no mocking the server itself)."""
import json
import socket
import time
import urllib.request

from services.opcua.health import start_health_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_health_endpoint_reports_status_provider_data():
    port = _free_port()
    server = start_health_server(port, status_provider=lambda: {"servers": {"p1": {"connected": True}}})
    try:
        time.sleep(0.05)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            body = json.loads(resp.read())
        assert body["status"] == "UP"
        assert body["service"] == "opcua"
        assert body["servers"]["p1"]["connected"] is True
    finally:
        server.shutdown()


def test_metrics_endpoint_503_without_prometheus_client():
    port = _free_port()
    server = start_health_server(port)
    try:
        time.sleep(0.05)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = True
            assert exc.code == 503
        assert raised, "expected 503 since prometheus_client is not installed in this environment"
    finally:
        server.shutdown()


def test_unknown_path_404():
    port = _free_port()
    server = start_health_server(port)
    try:
        time.sleep(0.05)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=2)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = True
            assert exc.code == 404
        assert raised
    finally:
        server.shutdown()
