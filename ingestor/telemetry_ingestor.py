#!/usr/bin/env python3
"""DIEP Telemetry Ingestor — MQTT → FastAPI /telemetry.

Bridges device telemetry into the platform's data plane. Subscribes to the
3-level telemetry topics (diep/<domain>/<device_id>), normalizes each device's
native payload onto the canonical TelemetryPayload schema, and POSTs it to
FastAPI /telemetry — which writes the TimescaleDB hypertable AND the Redis
`state:` mirror that powers /state, asset health, and the digital twins.

Mirrors the command dispatcher pattern (Kafka→MQTT→HTTP); this is the inbound
telemetry counterpart (MQTT→HTTP). Command/ack topics are 4 levels, so the
3-level subscription wildcard excludes them automatically.

Dependencies: paho-mqtt, requests
"""
import os
import json
import time
import logging

import requests
import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("diep-ingestor")

MQTT_BROKER = os.getenv("MQTT_BROKER", "diep-mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "diep-nodered")
MQTT_PASS = os.getenv("MQTT_PASS", "nodered-pass-2026")
FASTAPI_BASE = os.getenv("FASTAPI_BASE", "http://diep-fastapi:8000")
# Phase 9J: machine-client service token for the authenticated /telemetry route.
SERVICE_TOKEN = os.getenv("DIEP_SERVICE_TOKEN", "diep-service-dev-token-CHANGE-ME")
AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}

TELEMETRY_TOPIC = "diep/+/+"  # 3 levels = telemetry only (cmd/ack are 4 levels)

# Topics whose final path segment is not the registered device_id.
TOPIC_ID_OVERRIDES = {"meter1": "METER001"}

# Fields the FastAPI TelemetryPayload schema requires (all numeric, no defaults).
CANONICAL_FIELDS = ("voltage", "current", "power_kw", "frequency", "solar_kw",
                    "battery_soc", "grid_import_kw", "grid_export_kw")

# Phase 9-Schema: device-class extended fields the drivers publish on MQTT.
# Typed nullable telemetry columns:
EXTENDED_NUMERIC = ("power_factor", "energy_import_kwh", "energy_export_kwh",
                    "temperature", "soh")
# Device-specific long tail -> telemetry.metadata JSONB:
EXTRA_FIELDS = ("vehicle_soc", "connector_status", "session_energy_kwh",
                "load_kw", "setpoint_kw", "grid_connected", "mode")


def _num(value):
    """Return a float if value is numeric (bools are not), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def resolve_device_id(topic: str, payload: dict) -> str:
    """Prefer the device_id in the payload; fall back to the topic's last
    segment, applying overrides for sources that don't match a registered id."""
    if isinstance(payload.get("device_id"), str) and payload["device_id"]:
        return payload["device_id"]
    seg = topic.rsplit("/", 1)[-1]
    return TOPIC_ID_OVERRIDES.get(seg, seg)


def normalize(payload: dict) -> dict:
    """Map a device's native telemetry onto the canonical schema. Absent fields
    default to 0.0 because the API requires every field."""
    out = {field: 0.0 for field in CANONICAL_FIELDS}

    # 1. Direct canonical fields (smartmeter, EV charger, microgrid frequency/solar).
    for field in CANONICAL_FIELDS:
        value = _num(payload.get(field))
        if value is not None:
            out[field] = value

    # 2. Device-native aliases → canonical.
    soc = _num(payload.get("soc"))
    if soc is not None:                        # battery state of charge
        out["battery_soc"] = soc

    output_kw = _num(payload.get("output_kw"))
    if output_kw is not None:                  # solar inverter generation
        out["solar_kw"] = output_kw
        out["power_kw"] = output_kw
        out["grid_export_kw"] = max(0.0, output_kw)

    pcc_kw = _num(payload.get("pcc_kw"))
    if pcc_kw is not None:                      # microgrid point of common coupling
        out["power_kw"] = pcc_kw
        out["grid_import_kw"] = max(0.0, pcc_kw)
        out["grid_export_kw"] = max(0.0, -pcc_kw)

    # 3. Phase 9-Schema: forward device-class extended fields the drivers publish.
    for field in EXTENDED_NUMERIC:              # typed nullable columns
        value = _num(payload.get(field))
        if value is not None:
            out[field] = value
    if payload.get("state") is not None:
        out["state"] = str(payload["state"])
    # Device-specific long tail → metadata JSONB (telemetry.metadata).
    extra = {k: payload[k] for k in EXTRA_FIELDS if k in payload}
    if extra:
        out["extra"] = extra

    return out


def on_connect(client, userdata, flags, reason_code, properties):
    logger.info(f"MQTT connected (rc={reason_code}); subscribing {TELEMETRY_TOPIC}")
    client.subscribe(TELEMETRY_TOPIC, qos=0)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    logger.warning(f"MQTT disconnected (rc={reason_code})")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning(f"Dropping unparseable telemetry on {msg.topic}: {exc}")
        return
    if not isinstance(payload, dict):
        return

    device_id = resolve_device_id(msg.topic, payload)
    body = normalize(payload)
    body["device_id"] = device_id
    # Phase 9A: preserve the edge capture time (store-and-forward replays keep real timestamps).
    if payload.get("time"):
        body["time"] = payload["time"]

    try:
        resp = requests.post(f"{FASTAPI_BASE}/telemetry", json=body, headers=AUTH_HEADERS, timeout=5)
    except requests.RequestException as exc:
        logger.error(f"POST /telemetry failed for {device_id}: {exc}")
        return

    if resp.status_code == 201:
        logger.info(f"Ingested {msg.topic} -> {device_id} "
                    f"(power_kw={body['power_kw']}, soc={body['battery_soc']})")
    elif resp.status_code == 404:
        # Telemetry for a device not in the registry — skip quietly.
        logger.debug(f"Unknown device {device_id} from {msg.topic}; skipping")
    else:
        logger.warning(f"/telemetry returned {resp.status_code}: {resp.text[:200]}")


def _apply_mqtt_tls(client):
    """Phase 9J-S4: enable mutual TLS when MQTT_TLS=1 (cert identity, no password)."""
    if os.getenv("MQTT_TLS", "0") == "1":
        import ssl
        client.tls_set(
            ca_certs=os.getenv("MQTT_CA_CERTS"),
            certfile=os.getenv("MQTT_CLIENT_CERT"),
            keyfile=os.getenv("MQTT_CLIENT_KEY"),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="diep-telemetry-ingestor")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    _apply_mqtt_tls(client)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    delay = 2
    for attempt in range(30):
        try:
            logger.info(f"Connecting to MQTT {MQTT_BROKER}:{MQTT_PORT} (attempt {attempt + 1}/30)")
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            break
        except Exception as exc:
            logger.warning(f"MQTT connect attempt {attempt + 1} failed: {exc}")
            time.sleep(delay)
            delay = min(delay * 1.5, 30)
    else:
        raise RuntimeError("Failed to connect to MQTT after 30 attempts")

    logger.info("Telemetry ingestor running")
    client.loop_forever()


if __name__ == "__main__":
    main()
