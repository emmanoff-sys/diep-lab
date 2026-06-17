#!/usr/bin/env python3
"""DIEP Command Dispatcher — Kafka → MQTT → FastAPI.

Consumes commands from Kafka topic 'diep.commands', routes them to device-
specific MQTT topics via the command router (diep/<domain>/<device_id>/cmd),
then listens for device acks on MQTT and POSTs them back to FastAPI.

Command flow:
  1. Kafka consumer: diep.commands → parse JSON command
  2. Command router: map device_type → domain (charger, battery, solar, etc.)
  3. MQTT producer: publish to diep/<domain>/<device_id>/cmd
  4. MQTT consumer: listen on diep/+/+/ack
  5. HTTP POST: send ack to FastAPI /commands/{command_id}/ack

Dependencies: kafka-python, paho-mqtt, requests
"""
import os
import json
import time
import logging
import requests
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from kafka import KafkaConsumer
from kafka.errors import KafkaError

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('diep-dispatcher')

# --- Configuration from environment ---
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "diep-kafka:9094")  # 9J-S5: SASL listener
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT")
KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "diep")
# Phase 22 SEC-2 — no hardcoded credential; must come from .env (KAFKA_SASL_PASSWORD).
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "change-me-kafka-sasl-password")


def _kafka_security_kwargs():
    if KAFKA_SECURITY_PROTOCOL == "PLAINTEXT":
        return {}
    kw = {"security_protocol": KAFKA_SECURITY_PROTOCOL}
    if "SASL" in KAFKA_SECURITY_PROTOCOL:
        kw.update(sasl_mechanism=KAFKA_SASL_MECHANISM,
                  sasl_plain_username=KAFKA_SASL_USERNAME,
                  sasl_plain_password=KAFKA_SASL_PASSWORD)
    return kw


MQTT_BROKER = os.getenv("MQTT_BROKER", "diep-mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "diep-nodered")
MQTT_PASS = os.getenv("MQTT_PASS", "nodered-pass-2026")
FASTAPI_BASE = os.getenv("FASTAPI_BASE", "http://diep-fastapi:8000")
# Phase 9J: machine-client service token for the authenticated ack route.
SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")
AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}

COMMAND_TOPIC = "diep.commands"
ACK_SUBSCRIBE_TOPIC = "diep/+/+/ack"

# Device type → MQTT domain mapping
DOMAIN_MAP = {
    "ev_charger": "charger",
    "battery": "battery",
    "solar_inverter": "solar",
    "microgrid": "microgrid",
}


def get_mqtt_domain(device_type):
    """Map device_type to MQTT domain. Fallback to device_type if unknown."""
    return DOMAIN_MAP.get(device_type, device_type)


def get_command_topic(device_type, device_id):
    """Construct MQTT command topic: diep/<domain>/<device_id>/cmd"""
    domain = get_mqtt_domain(device_type)
    return f"diep/{domain}/{device_id}/cmd"


class CommandDispatcher:
    """Kafka → MQTT → FastAPI command dispatcher."""

    def __init__(self):
        self.mqtt_client = None
        self.kafka_consumer = None
        self._setup_mqtt()
        self._setup_kafka()

    def _setup_mqtt(self):
        """Initialize MQTT client."""
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if MQTT_USER:
            self.mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
        # Phase 9J-S4: mutual TLS when MQTT_TLS=1 (cert identity, no password).
        if os.getenv("MQTT_TLS", "0") == "1":
            import ssl
            self.mqtt_client.tls_set(
                ca_certs=os.getenv("MQTT_CA_CERTS"),
                certfile=os.getenv("MQTT_CLIENT_CERT"),
                keyfile=os.getenv("MQTT_CLIENT_KEY"),
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect

        logger.info(f"Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
        self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        self.mqtt_client.loop_start()

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        """Subscribe to ack topics after MQTT connect."""
        logger.info(f"MQTT connected (rc={reason_code}), subscribing to {ACK_SUBSCRIBE_TOPIC}")
        client.subscribe(ACK_SUBSCRIBE_TOPIC, qos=1)

    def _on_mqtt_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """Log MQTT disconnect."""
        logger.warning(f"MQTT disconnected (rc={reason_code})")

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT ack messages."""
        try:
            ack_payload = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse MQTT ack: {e}")
            return

        command_id = ack_payload.get("command_id")
        status = ack_payload.get("status")
        error = ack_payload.get("error")

        logger.info(f"Device ack: {command_id} = {status}")
        self._post_ack_to_fastapi(command_id, status, error)

    def _post_ack_to_fastapi(self, command_id, status, error):
        """POST device ack back to FastAPI."""
        url = f"{FASTAPI_BASE}/commands/{command_id}/ack"
        payload = {"status": status, "error": error}

        try:
            resp = requests.post(url, json=payload, headers=AUTH_HEADERS, timeout=5)
            if resp.status_code == 200:
                logger.info(f"Posted ack {command_id} to FastAPI")
            else:
                logger.warning(f"FastAPI ack POST failed: {resp.status_code} {resp.text}")
        except requests.RequestException as e:
            logger.error(f"Failed to POST ack to FastAPI: {e}")

    def _setup_kafka(self):
        """Initialize Kafka consumer for command topic with retry logic."""
        max_retries = 30
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to Kafka {KAFKA_BOOTSTRAP} (attempt {attempt + 1}/{max_retries})")
                self.kafka_consumer = KafkaConsumer(
                    COMMAND_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP,
                    group_id="diep-command-dispatcher",
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="earliest",
                    enable_auto_commit=True,
                    max_poll_records=1,
                    consumer_timeout_ms=5000,
                    connections_max_idle_ms=540000,  # 9 minutes idle timeout
                    **_kafka_security_kwargs(),
                )
                logger.info("Kafka consumer ready")
                return
            except Exception as e:
                logger.warning(f"Kafka connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30)  # Cap at 30 seconds
                else:
                    raise RuntimeError(f"Failed to connect to Kafka after {max_retries} attempts")


    def dispatch_command_to_mqtt(self, command):
        """Dispatch a command to the appropriate MQTT topic."""
        command_id = command.get("command_id")
        device_id = command.get("device_id")
        device_type = command.get("device_type")

        if not all([command_id, device_id, device_type]):
            logger.error(f"Incomplete command: {command}")
            return False

        topic = get_command_topic(device_type, device_id)
        payload = json.dumps(command)

        try:
            self.mqtt_client.publish(topic, payload, qos=1)
            logger.info(f"Dispatched {command.get('command_type')} for {device_id} to {topic}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish command to MQTT: {e}")
            return False

    def run(self):
        """Main event loop: consume Kafka commands and dispatch to MQTT."""
        logger.info("Starting command dispatcher main loop")
        try:
            # The consumer is configured with consumer_timeout_ms, so the inner
            # iterator raises StopIteration after an idle window. Wrap it in an
            # outer loop so an idle period just re-enters polling instead of
            # terminating the process (which Docker then restart-loops).
            while True:
                for message in self.kafka_consumer:
                    if message is None:
                        continue

                    command = message.value
                    logger.info(f"Received command from Kafka: {command.get('command_type')} "
                               f"for {command.get('device_id')}")
                    self.dispatch_command_to_mqtt(command)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down dispatcher")
        if self.kafka_consumer:
            self.kafka_consumer.close()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()


if __name__ == "__main__":
    dispatcher = CommandDispatcher()
    dispatcher.run()
