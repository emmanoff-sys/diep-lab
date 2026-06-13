"""DIEP battery storage simulator — bidirectional device.

Participates in the command/control plane (see ev_charger.py for the pattern):
  - SUBSCRIBES to  diep/battery/<id>/cmd
  - PUBLISHES acks to diep/battery/<id>/ack
  - PUBLISHES telemetry to diep/battery/<id> every few seconds

Command vocabulary (must match ALLOWED_COMMANDS['battery'] in the API):
  charge          params: {"power_kw": <float, optional>}
  discharge       params: {"power_kw": <float, optional>}
  set_soc_target  params: {"soc_target": <float 0-100>}
  idle            params: {}
"""
import os
import time
import json
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_USER = os.getenv("MQTT_USER", "diep-device")
MQTT_PASS = os.getenv("MQTT_PASS", "device-pass-2026")
DEVICE_ID = os.getenv("DEVICE_ID", "BAT001")
CAPACITY_KWH = float(os.getenv("CAPACITY_KWH", "100"))
MAX_POWER_KW = float(os.getenv("MAX_POWER_KW", "50"))
TELEMETRY_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "5"))

BASE_TOPIC = f"diep/battery/{DEVICE_ID}"
CMD_TOPIC = f"{BASE_TOPIC}/cmd"
ACK_TOPIC = f"{BASE_TOPIC}/ack"

state = {
    "mode": "idle",        # idle | charging | discharging
    "power_kw": 0.0,
    "soc": 50.0,
    "soc_target": 100.0,
}


def apply_command(cmd):
    """Execute a command against battery state. Returns (status, error)."""
    ctype = cmd.get("command_type")
    params = cmd.get("params") or {}

    if ctype == "charge":
        state["power_kw"] = min(float(params.get("power_kw", MAX_POWER_KW)), MAX_POWER_KW)
        state["mode"] = "charging"
        return "ACKED", None

    if ctype == "discharge":
        state["power_kw"] = min(float(params.get("power_kw", MAX_POWER_KW)), MAX_POWER_KW)
        state["mode"] = "discharging"
        return "ACKED", None

    if ctype == "set_soc_target":
        if "soc_target" not in params:
            return "FAILED", "set_soc_target requires params.soc_target"
        state["soc_target"] = max(0.0, min(100.0, float(params["soc_target"])))
        return "ACKED", None

    if ctype == "idle":
        state["mode"] = "idle"
        state["power_kw"] = 0.0
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


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"battery-{DEVICE_ID}")
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(BROKER, 1883, 60)
client.loop_start()

while True:
    # Integrate state of charge from the active power flow.
    delta_soc = state["power_kw"] * TELEMETRY_INTERVAL / 3600.0 / CAPACITY_KWH * 100.0
    if state["mode"] == "charging":
        state["soc"] = round(min(state["soc_target"], state["soc"] + delta_soc), 2)
        if state["soc"] >= state["soc_target"]:
            state["mode"], state["power_kw"] = "idle", 0.0
    elif state["mode"] == "discharging":
        state["soc"] = round(max(0.0, state["soc"] - delta_soc), 2)
        if state["soc"] <= 0.0:
            state["mode"], state["power_kw"] = "idle", 0.0
    else:
        state["power_kw"] = 0.0

    # Signed power: + = charging (import), - = discharging (export).
    signed_power = (state["power_kw"] if state["mode"] == "charging"
                    else -state["power_kw"] if state["mode"] == "discharging" else 0.0)

    telemetry = {
        "device_id": DEVICE_ID,
        "mode": state["mode"],
        "power_kw": round(signed_power, 2),
        "soc": state["soc"],
        "soc_target": state["soc_target"],
        "capacity_kwh": CAPACITY_KWH,
    }
    client.publish(BASE_TOPIC, json.dumps(telemetry))
    print(f"[{DEVICE_ID}] telemetry {telemetry}")
    time.sleep(TELEMETRY_INTERVAL)
