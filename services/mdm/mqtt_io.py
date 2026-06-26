"""MDM MQTT I/O — subscribes to the telemetry wildcard, runs envelope-shaped
messages through MdmPipeline, publishes the trusted output.

paho-mqtt is imported lazily inside MqttIo (not at module level) so this
module is importable without it; only actually running the service needs it.
Structure mirrors ingestor/telemetry_ingestor.py (same broker, same wildcard,
same TLS option handling) since MDM is an independent subscriber to the same
topics, not a replacement for the ingestor's HTTP path — see
AMI_INGEST_PHASE4_CONTRACT.md §7 / MDM_DESIGN.md for why both consumers
coexist this phase.
"""
from __future__ import annotations

import json
import logging

from .config import Settings
from .pipeline import MdmPipeline

logger = logging.getLogger("diep-mdm.mqtt")


def is_envelope_payload(payload: dict) -> bool:
    return "schema_version" in payload and "measurements" in payload


def domain_from_topic(topic: str) -> str:
    """diep/<domain>/<device_id> -> <domain>. Falls back to 'device' for a
    topic that doesn't match the expected 3-level shape (defensive only —
    the subscription wildcard already constrains this)."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 3 else "device"


class MqttIo:
    def __init__(self, pipeline: MdmPipeline | None = None):
        self.pipeline = pipeline or MdmPipeline()
        self.client = None

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        logger.info("MQTT connected (rc=%s); subscribing %s", reason_code, Settings.TELEMETRY_TOPIC)
        client.subscribe(Settings.TELEMETRY_TOPIC, qos=0)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("MQTT disconnected (rc=%s)", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("Dropping unparseable message on %s: %s", msg.topic, exc)
            return
        if not isinstance(payload, dict) or not is_envelope_payload(payload):
            return  # legacy flat payload — not this driver's contract; ingestor handles it

        domain = domain_from_topic(msg.topic)
        result = self.pipeline.process(payload, domain)
        if not result.accepted:
            logger.debug("Rejected/dropped %s on %s: %s", payload.get("device_id"), msg.topic, result.reason)
            return
        client.publish(result.topic, MdmPipeline.serialize(result.payload), qos=0)
        logger.info("Published trusted reading for %s -> %s", payload.get("device_id"), result.topic)

    def _apply_tls(self, client):
        if Settings.MQTT_TLS:
            import ssl
            client.tls_set(
                ca_certs=Settings.MQTT_CA_CERTS,
                certfile=Settings.MQTT_CLIENT_CERT,
                keyfile=Settings.MQTT_CLIENT_KEY,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

    def run_forever(self) -> None:
        import time
        import paho.mqtt.client as mqtt

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="diep-mdm")
        if Settings.MQTT_USER:
            self.client.username_pw_set(Settings.MQTT_USER, Settings.MQTT_PASS)
        self._apply_tls(self.client)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        delay = 2
        for attempt in range(30):
            try:
                logger.info("Connecting to MQTT %s:%s (attempt %d/30)", Settings.MQTT_BROKER, Settings.MQTT_PORT, attempt + 1)
                self.client.connect(Settings.MQTT_BROKER, Settings.MQTT_PORT, keepalive=60)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("MQTT connect attempt %d failed: %s", attempt + 1, exc)
                time.sleep(delay)
                delay = min(delay * 1.5, 30)
        else:
            raise RuntimeError("Failed to connect to MQTT after 30 attempts")

        logger.info("MDM running")
        self.client.loop_forever()
