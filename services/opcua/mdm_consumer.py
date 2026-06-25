"""Post-SIT stabilization sprint, Work Item 5 — consumes MDM's "trusted"
MQTT stream and feeds it into the same MeasurementSink the OPC UA client
side already uses.

paho-mqtt is real and already live-tested in this environment (unlike
`asyncua`, which can't be installed in this dev shell -- see
services/opcua/VALIDATION.md) -- structure mirrors the established pattern
in services/mdm/mqtt_io.py and the (post-redesign) ingestor: mTLS, qos=0,
reconnect-with-backoff. Deliberately does **not** stand up a server-side
OPC UA address space (`asyncua.Server`) to re-publish these values to
external OPC UA clients -- that's a different, larger piece of work the
literal work item doesn't ask for (see VALIDATION.md addendum). This module
only "consumes" -- the same scope the work item names -- and makes the
result observable via the existing /health and /metrics surface.

paho-mqtt is imported lazily, only inside `MdmConsumer.start()` (same
convention as the rest of this codebase for optional/heavy dependencies --
see services/mdm/mqtt_io.py), so this module stays importable without it.
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time

from .measurement import MeasurementSink, build_measurement_from_trusted

logger = logging.getLogger("diep-opcua.mdm_consumer")


def domain_from_topic(topic: str) -> str:
    """diep/<domain>/<device_id>/trusted -> <domain>. Falls back to 'device'
    for a topic that doesn't match the expected 4-level shape (defensive
    only -- the subscription wildcard already constrains this)."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 4 else "device"


class MdmConsumer:
    def __init__(self, sink: MeasurementSink, *, broker: str, port: int, topic: str,
                 tls: bool = False, ca_certs: str | None = None,
                 client_cert: str | None = None, client_key: str | None = None,
                 username: str | None = None, password: str | None = None):
        self.sink = sink
        self.broker = broker
        self.port = port
        self.topic = topic
        self.tls = tls
        self.ca_certs = ca_certs
        self.client_cert = client_cert
        self.client_key = client_key
        self.username = username
        self.password = password
        self.client = None
        self._stop_event = threading.Event()
        self._connect_thread: threading.Thread | None = None

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        logger.info("MQTT connected (rc=%s); subscribing %s", reason_code, self.topic)
        client.subscribe(self.topic, qos=0)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("MQTT disconnected (rc=%s)", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("Dropping unparseable trusted message on %s: %s", msg.topic, exc)
            return
        if not isinstance(payload, dict):
            return

        domain = domain_from_topic(msg.topic)
        try:
            measurements = build_measurement_from_trusted(payload, domain=domain)
        except Exception as exc:  # noqa: BLE001 -- one malformed message must never kill this consumer
            logger.error("Failed to map trusted message on %s: %s", msg.topic, exc)
            return
        for measurement in measurements:
            self.sink.emit(measurement)

    def _apply_tls(self, client):
        if self.tls:
            client.tls_set(
                ca_certs=self.ca_certs,
                certfile=self.client_cert,
                keyfile=self.client_key,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

    def _run(self) -> None:
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="diep-opcua-mdm-consumer")
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        self._apply_tls(self.client)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        delay = 2.0
        while not self._stop_event.is_set():
            try:
                logger.info("Connecting to MQTT %s:%s", self.broker, self.port)
                self.client.connect(self.broker, self.port, keepalive=60)
                break
            except Exception as exc:  # noqa: BLE001 -- retry with backoff, never crash the worker
                logger.warning("MQTT connect failed: %s; retrying in %.1fs", exc, delay)
                if self._stop_event.wait(delay):
                    return
                delay = min(delay * 1.5, 30.0)
        else:
            return

        self.client.loop_start()
        logger.info("MDM trusted-stream consumer running")

    def start(self) -> None:
        self._connect_thread = threading.Thread(target=self._run, name="opcua-mdm-consumer", daemon=True)
        self._connect_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
        if self._connect_thread is not None:
            self._connect_thread.join(timeout=5)
