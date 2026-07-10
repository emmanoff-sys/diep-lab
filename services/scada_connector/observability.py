"""OA-097 — connector health HTTP server.

Lightweight HTTP server providing /health, /ready, /live, and /metrics
endpoints for any connector that holds a ConnectorLifecycle instance.
Runs in a daemon thread; does not block the connector main loop.

Used by all three connectors (SCADA, GIS, AMI) — the interface is generic
over ConnectorLifecycle from the shared framework.

Endpoint contract:
  GET /health  — 200 with JSON ConnectorHealth snapshot (always)
  GET /ready   — 200 if lifecycle.health().healthy else 503
  GET /live    — 200 always (liveness probe never fails)
  GET /metrics — 200 with Prometheus text; 503 if prometheus_client absent
  GET *        — 404
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .framework import ConnectorHealth, ConnectorLifecycle

logger = logging.getLogger("re-os.connector.health")

_BIND_HOST = "0.0.0.0"  # noqa: S104  # nosec B104 — health endpoint binds to all interfaces; required for container health-check reachability

__all__ = [
    "ConnectorHealthServer",
    "start_connector_health_server",
]


class _ConnectorHealthHandler(BaseHTTPRequestHandler):
    server_version = "re-os-connector-health/1.0"
    # Injected by start_connector_health_server before serving
    _health_provider: Callable[[], ConnectorHealth] = None  # type: ignore[assignment]

    def log_message(self, format, *args):  # noqa: A002
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        if self.path == "/health":
            health = self._health_provider()
            body: dict = {
                "status": "UP" if health.healthy else "DOWN",
                "connector_id": health.connector_id,
                "connector_status": health.status,
                "healthy": health.healthy,
                "session_count": health.session_count,
                "events_submitted": health.events_submitted,
                "events_rejected": health.events_rejected,
                "events_dead_lettered": health.events_dead_lettered,
                "last_error": health.last_error,
            }
            self._respond_json(200, body)

        elif self.path == "/ready":
            health = self._health_provider()
            code = 200 if health.healthy else 503
            self._respond_json(code, {"ready": health.healthy})

        elif self.path == "/live":
            self._respond_json(200, {"live": True})

        elif self.path == "/metrics":
            self._respond_metrics()

        else:
            self._respond_json(404, {"error": "not found"})

    def _respond_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _respond_metrics(self) -> None:
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        except ImportError:
            self._respond_json(503, {"error": "prometheus_client not installed"})
            return
        payload = generate_latest()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ConnectorHealthServer:
    """Manages the lifecycle of a connector health HTTP server."""

    def __init__(self, lifecycle: ConnectorLifecycle, port: int) -> None:
        self._lifecycle = lifecycle
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the health server in a daemon background thread."""
        if self._server is not None:
            raise RuntimeError("health server already started")
        handler = type(
            "_BoundHandler",
            (_ConnectorHealthHandler,),
            {"_health_provider": staticmethod(self._lifecycle.health)},
        )
        self._server = ThreadingHTTPServer((_BIND_HOST, self._port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"connector-health-{self._lifecycle.config.connector_id}",
        )
        self._thread.start()
        logger.info(
            "connector health server started for %s on port %d",
            self._lifecycle.config.connector_id,
            self._port,
        )

    def stop(self) -> None:
        """Shut down the health server gracefully."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
            logger.info(
                "connector health server stopped for %s",
                self._lifecycle.config.connector_id,
            )


def start_connector_health_server(
    lifecycle: ConnectorLifecycle,
    port: int,
) -> ConnectorHealthServer:
    """Convenience: create, start, and return a ConnectorHealthServer."""
    server = ConnectorHealthServer(lifecycle, port)
    server.start()
    return server
