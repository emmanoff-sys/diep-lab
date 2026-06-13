"""DIEP EV charger simulator — bidirectional device.

Unlike the publish-only smartmeter sim, this device participates in the
command/control plane:
  - SUBSCRIBES to  diep/charger/<id>/cmd   (commands dispatched via Node-RED)
  - PUBLISHES acks to diep/charger/<id>/ack (consumed by Node-RED -> FastAPI)
  - PUBLISHES telemetry to diep/charger/<id> every few seconds

Command vocabulary (must match ALLOWED_COMMANDS['ev_charger'] in the API):
  start_charging  params: {"max_power_kw": <float, optional>}
  stop_charging   params: {}
  set_limit       params: {"max_power_kw": <float>}
"""
import os
import ssl
import time
import json
import random
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "diep-device")
MQTT_PASS = os.getenv("MQTT_PASS", "device-pass-2026")
MQTT_TLS = os.getenv("MQTT_TLS", "0") == "1"
DEVICE_ID = os.getenv("DEVICE_ID", "EV001")
MAX_POWER_KW = float(os.getenv("MAX_POWER_KW", "22"))
TELEMETRY_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "5"))

BASE_TOPIC = f"diep/charger/{DEVICE_ID}"
CMD_TOPIC = f"{BASE_TOPIC}/cmd"
ACK_TOPIC = f"{BASE_TOPIC}/ack"

# Mutable charger state.
state = {
    "charging": False,
    "power_limit_kw": MAX_POWER_KW,
    "power_kw": 0.0,
    "session_energy_kwh": 0.0,
    "vehicle_soc": 35.0,
}


def apply_command(cmd):
    """Execute a command against charger state. Returns (status, error)."""
    ctype = cmd.get("command_type")
    params = cmd.get("params") or {}

    if ctype == "start_charging":
        limit = float(params.get("max_power_kw", state["power_limit_kw"]))
        state["power_limit_kw"] = min(limit, MAX_POWER_KW)
        state["charging"] = True
        return "ACKED", None

    if ctype == "stop_charging":
        state["charging"] = False
        state["power_kw"] = 0.0
        return "ACKED", None

    if ctype == "set_limit":
        if "max_power_kw" not in params:
            return "FAILED", "set_limit requires params.max_power_kw"
        state["power_limit_kw"] = min(float(params["max_power_kw"]), MAX_POWER_KW)
        return "ACKED", None

    return "FAILED", f"unsupported command_type '{ctype}'"


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[{DEVICE_ID}] connected to MQTT ({reason_code}), subscribing {CMD_TOPIC}")
    client.subscribe(CMD_TOPIC, qos=1)


def on_message(client, userdata, msg):
    try:
        cmd = json.loads(msg.payload.decode())
    except (ValueError, UnicodeDecodeError) as e:
        print(f"[{DEVICE_ID}] dropping unparseable command: {e}")
        return

    command_id = cmd.get("command_id")
    print(f"[{DEVICE_ID}] received command {cmd.get('command_type')} ({command_id})")
    status, error = apply_command(cmd)

    ack = {
        "command_id": command_id,
        "device_id": DEVICE_ID,
        "status": status,
        "error": error,
        "acked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    client.publish(ACK_TOPIC, json.dumps(ack), qos=1)
    print(f"[{DEVICE_ID}] -> ack {status} for {command_id}"
          + (f": {error}" if error else ""))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"charger-{DEVICE_ID}")
client.on_connect = on_connect
client.on_message = on_message
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)
# Phase 9J-S4: mutual TLS when MQTT_TLS=1 (cert identity, no password).
if MQTT_TLS:
    client.tls_set(
        ca_certs=os.getenv("MQTT_CA_CERTS"),
        certfile=os.getenv("MQTT_CLIENT_CERT"),
        keyfile=os.getenv("MQTT_CLIENT_KEY"),
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
client.connect(BROKER, MQTT_PORT, 60)
client.loop_start()

while True:
    if state["charging"]:
        # Draw near the limit with a little jitter; trickle down as SoC fills.
        soc_factor = max(0.1, (100.0 - state["vehicle_soc"]) / 100.0)
        state["power_kw"] = round(state["power_limit_kw"] * soc_factor
                                  * random.uniform(0.9, 1.0), 2)
        state["session_energy_kwh"] = round(
            state["session_energy_kwh"]
            + state["power_kw"] * TELEMETRY_INTERVAL / 3600.0, 4)
        state["vehicle_soc"] = round(
            min(100.0, state["vehicle_soc"] + state["power_kw"] * 0.02), 2)
        if state["vehicle_soc"] >= 100.0:
            state["charging"] = False
            state["power_kw"] = 0.0
    else:
        state["power_kw"] = 0.0

    telemetry = {
        "device_id": DEVICE_ID,
        "charging": state["charging"],
        "power_kw": state["power_kw"],
        "power_limit_kw": state["power_limit_kw"],
        "session_energy_kwh": state["session_energy_kwh"],
        "vehicle_soc": state["vehicle_soc"],
    }
    client.publish(BASE_TOPIC, json.dumps(telemetry))
    print(f"[{DEVICE_ID}] telemetry {telemetry}")
    time.sleep(TELEMETRY_INTERVAL)
