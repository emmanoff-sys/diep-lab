"""DIEP smart-meter simulator (ADMS M2 — last-gasp capable).

Publishes canonical telemetry to diep/smartmeter/<DEVICE_ID> and, crucially for
OMS, emits a "last gasp" message (state=LAST_GASP) when it loses power — either
on a remote_disconnect command (operator/OMS-driven) or as a dying-gasp on
SIGTERM (container stop / simulated feeder loss). The ingestor stores `state`,
so OMS detection (POST /oms/detect) sees the outage.

mTLS + command/ack follow the ev_charger.py pattern (broker is mTLS-only on
8883). Commands handled: remote_disconnect, remote_connect, read_only.
"""
import os
import sys
import ssl
import json
import time
import signal
import random

import paho.mqtt.client as mqtt

DEVICE_ID = os.getenv("DEVICE_ID", "METER001")
BROKER = os.getenv("MQTT_BROKER", "diep-mqtt")
PORT = int(os.getenv("MQTT_PORT", "8883"))
USE_TLS = os.getenv("MQTT_TLS", "1") == "1"
INTERVAL = float(os.getenv("TELEMETRY_INTERVAL", "5"))

TOPIC = f"diep/smartmeter/{DEVICE_ID}"
CMD_TOPIC = f"{TOPIC}/cmd"
ACK_TOPIC = f"{TOPIC}/ack"

energized = True            # power present at the meter
battery_soc = 50.0
energy_import_kwh = 1000.0
energy_export_kwh = 200.0

client = mqtt.Client(client_id=DEVICE_ID)


def _publish_last_gasp(reason: str) -> None:
    """The dying gasp: a final, retained-ish message announcing power loss."""
    payload = {
        "device_id": DEVICE_ID,
        "state": "LAST_GASP",
        "voltage": 0.0, "current": 0.0, "power_kw": 0.0, "frequency": 0.0,
        "solar_kw": 0.0, "battery_soc": round(battery_soc, 2),
        "grid_import_kw": 0.0, "grid_export_kw": 0.0,
        "energy_import_kwh": round(energy_import_kwh, 3),
        "energy_export_kwh": round(energy_export_kwh, 3),
        "reason": reason,
    }
    client.publish(TOPIC, json.dumps(payload), qos=1)
    print(f"[{DEVICE_ID}] LAST_GASP ({reason})", flush=True)


def _ack(command_id, status="ACKED", error=None):
    client.publish(ACK_TOPIC, json.dumps({
        "command_id": command_id, "device_id": DEVICE_ID,
        "status": status, "error": error,
    }), qos=1)


def on_connect(c, userdata, flags, rc):
    c.subscribe(CMD_TOPIC, qos=1)
    print(f"[{DEVICE_ID}] connected rc={rc}, subscribed {CMD_TOPIC}", flush=True)


def on_message(c, userdata, msg):
    global energized
    try:
        cmd = json.loads(msg.payload.decode())
    except Exception:
        return
    ctype = cmd.get("command_type")
    cid = cmd.get("command_id")
    if ctype == "remote_disconnect":
        energized = False
        _publish_last_gasp("remote_disconnect")
        _ack(cid)
    elif ctype == "remote_connect":
        energized = True
        _ack(cid)
        print(f"[{DEVICE_ID}] reconnected", flush=True)
    elif ctype == "read_only":
        _ack(cid)
    else:
        _ack(cid, status="FAILED", error=f"unsupported command '{ctype}'")


def _on_signal(signum, frame):
    # Graceful dying-gasp on container stop / feeder loss.
    _publish_last_gasp("shutdown")
    time.sleep(0.3)  # give QoS-1 publish a moment to flush
    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)

client.on_connect = on_connect
client.on_message = on_message

if USE_TLS:
    client.tls_set(
        ca_certs=os.getenv("MQTT_CA_CERTS", "/certs/ca.crt"),
        certfile=os.getenv("MQTT_CLIENT_CERT", f"/certs/{DEVICE_ID}.crt"),
        keyfile=os.getenv("MQTT_CLIENT_KEY", f"/certs/{DEVICE_ID}.key"),
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
else:
    client.username_pw_set(os.getenv("MQTT_USER", "diep-device"),
                           os.getenv("MQTT_PASS", "device-pass-2026"))

client.connect(BROKER, PORT, 60)
client.loop_start()

while True:
    if energized:
        load_kw = round(random.uniform(1.0, 5.0), 2)
        solar_kw = round(random.uniform(0.0, 10.0), 2)
        net = solar_kw - load_kw
        battery_soc = max(0.0, min(100.0, battery_soc + (net * 0.1 if net > 0 else net * 0.05)))
        grid_import = max(0.0, load_kw - solar_kw)
        grid_export = max(0.0, solar_kw - load_kw)
        energy_import_kwh += grid_import * INTERVAL / 3600.0
        energy_export_kwh += grid_export * INTERVAL / 3600.0
        payload = {
            "device_id": DEVICE_ID,
            "voltage": round(random.uniform(220, 235), 2),
            "current": round(load_kw * 4, 2),
            "power_kw": load_kw,
            "frequency": round(random.uniform(49.8, 50.2), 2),
            "solar_kw": solar_kw,
            "battery_soc": round(battery_soc, 2),
            "grid_import_kw": grid_import,
            "grid_export_kw": grid_export,
            "power_factor": round(random.uniform(0.95, 1.0), 3),
            "energy_import_kwh": round(energy_import_kwh, 3),
            "energy_export_kwh": round(energy_export_kwh, 3),
            "state": "OK",
        }
        client.publish(TOPIC, json.dumps(payload), qos=0)
        print(payload, flush=True)
    # When de-energized we stay silent (the last gasp already announced it),
    # which is exactly the heartbeat-gap OMS also detects.
    time.sleep(INTERVAL)
