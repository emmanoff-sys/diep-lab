"""MQTT transport for edge drivers — paho wrapper, TLS-ready.

TLS / mutual-TLS hooks are present but optional so the SDK works against the
current plaintext lab broker today and against the hardened broker after Phase 9J
(per-device client certificates) with config only — no code change.
"""
from __future__ import annotations

import os
import ssl
import logging

logger = logging.getLogger("diep-driver.mqtt")


class MqttTransport:
    def __init__(
        self,
        client_id: str,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        tls: bool | None = None,
        ca_certs: str | None = None,
        certfile: str | None = None,
        keyfile: str | None = None,
    ):
        # Imported lazily so the SDK (BaseDriver, decoders, registry) is usable
        # without paho installed — only the MQTT runtime needs it.
        import paho.mqtt.client as mqtt

        self.host = host or os.getenv("MQTT_BROKER", "diep-mqtt")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._subscriptions: list[tuple[str, int]] = []  # for re-subscribe on reconnect
        self.connected = False  # tracked for edge store-and-forward (9A)

        username = username or os.getenv("MQTT_USER")
        password = password or os.getenv("MQTT_PASS")
        if username:
            self.client.username_pw_set(username, password)

        # TLS / mTLS — enabled by env (MQTT_TLS=1) or explicit args (Phase 9J).
        use_tls = tls if tls is not None else os.getenv("MQTT_TLS", "0") == "1"
        if use_tls:
            self.client.tls_set(
                ca_certs=ca_certs or os.getenv("MQTT_CA_CERTS"),
                certfile=certfile or os.getenv("MQTT_CLIENT_CERT"),
                keyfile=keyfile or os.getenv("MQTT_CLIENT_KEY"),
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
            if self.port == 1883:
                self.port = 8883  # default MQTT-over-TLS port

    def connect(self):
        logger.info("MQTT connecting %s:%s", self.host, self.port)
        # Re-subscribe on every (re)connect: paho does NOT re-issue SUBSCRIBE after
        # an auto-reconnect, so a long-running driver would silently stop receiving
        # commands (telemetry publishes keep working). on_connect restores them.
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = True
        for topic, qos in self._subscriptions:
            client.subscribe(topic, qos=qos)
        if self._subscriptions:
            logger.info("MQTT (re)subscribed to %d topic(s)", len(self._subscriptions))

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        logger.warning("MQTT disconnected")

    def publish(self, topic: str, payload: str, qos: int = 0):
        self.client.publish(topic, payload, qos=qos)

    def subscribe(self, topic: str, callback, qos: int = 1):
        self.client.message_callback_add(topic, callback)
        self._subscriptions.append((topic, qos))
        self.client.subscribe(topic, qos=qos)

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
