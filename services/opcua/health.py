"""OPC UA connector health + metrics HTTP endpoint — stdlib http.server only,
same lightweight pattern as services/mdm/health.py (no new web-framework
dependency). /health reports per-server connection state plus the sink's
latest-value snapshot for a quick eyeball without a Prometheus query.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("diep-opcua.health")


class _Handler(BaseHTTPRequestHandler):
    server_version = "diep-opcua-health/1.0"
    status_provider = None  # set by start_health_server; callable -> dict

    def log_message(self, format, *args):  # noqa: A002 — match BaseHTTPRequestHandler's signature
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        if self.path == "/health":
            body = self.status_provider() if self.status_provider else {}
            self._respond_json(200, {"status": "UP", "service": "opcua", **body})
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
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        except ImportError:
            self._respond_json(503, {"error": "prometheus_client not installed"})
            return
        payload = generate_latest()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def start_health_server(port: int, status_provider=None) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"status_provider": staticmethod(status_provider) if status_provider else None})
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="opcua-health")
    thread.start()
    logger.info("health/metrics server listening on :%d (/health, /metrics)", port)
    return server
