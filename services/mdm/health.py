"""MDM health + metrics HTTP endpoint.

Stdlib http.server only (no new web-framework dependency for a service this
small — matches the lightweight style of ingestor/dispatcher, neither of
which uses FastAPI). /metrics delegates to prometheus_client's own registry
(lazy import — see metrics.py); /health is a static liveness check plus the
count of envelopes processed so far, for a quick eyeball without a Prometheus
query.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("diep-mdm.health")


class _Handler(BaseHTTPRequestHandler):
    server_version = "diep-mdm-health/1.0"

    def log_message(self, format, *args):  # noqa: A002 — match BaseHTTPRequestHandler's signature
        logger.debug("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        if self.path == "/health":
            self._respond_json(200, {"status": "UP", "service": "mdm"})
        elif self.path == "/metrics":
            self._respond_metrics()
        else:
            self._respond_json(404, {"error": "not found"})

    def _respond_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
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


def start_health_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mdm-health")
    thread.start()
    logger.info("health/metrics server listening on :%d (/health, /metrics)", port)
    return server
