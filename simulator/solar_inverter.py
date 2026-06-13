"""DIEP solar inverter simulator — bidirectional device.

Participates in the command/control plane (see ev_charger.py for the pattern):
  - SUBSCRIBES to  diep/solar/<id>/cmd
  - PUBLISHES acks to diep/solar/<id>/ack
  - PUBLISHES telemetry to diep/solar/<id> every few seconds

Command vocabulary (must match ALLOWED_COMMANDS['solar_inverter'] in the API):
  curtail    params: {"limit_kw": <float, optional>}   # default: half of capacity
  set_limit  params: {"max_power_kw": <float>}          # active-power cap
  resume     params: {}                                 # clear curtailment

Output follows a simulated daily irradiance curve, capped by the active limit.
"""
import os
import math
import time
import json
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_USER = os.getenv("MQTT_USER", "diep-device")
MQTT_PASS = os.getenv("MQTT_PASS", "device-pass-2026")
DEVICE_ID = os.getenv("DEVICE_ID", "INV001")
CAPACITY_KW = float(os.getenv("CAPACITY_KW", "10"))
TELEMETRY_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "5"))

BASE_TOPIC = f"diep/solar/{DEVICE_ID}"
CMD_TOPIC = f"{BASE_TOPIC}/cmd"
ACK_TOPIC = f"{BASE_TOPIC}/ack"

state = {
    "limit_kw": CAPACITY_KW,   # active-power cap
    "curtailed": False,
    "output_kw": 0.0,
}


def available_kw():
    """Simulated array potential from a daytime irradiance curve (sinusoid
    over a 120s synthetic 'day' so the curve is observable in a lab)."""
    phase = (time.time() % 120) / 120.0 * math.pi  # 0..pi -> sunrise..sunset
    return round(CAPACITY_KW * max(0.0, math.sin(phase)), 2)


def apply_command(cmd):
    """Execute a command against inverter state. Returns (status, error)."""
    ctype = cmd.get("command_type")
    params = cmd.get("params") or {}

    if ctype == "curtail":
        limit = float(params.get("limit_kw", CAPACITY_KW * 0.5))
        state["limit_kw"] = max(0.0, min(limit, CAPACITY_KW))
        state["curtailed"] = True
        return "ACKED", None

    if ctype == "set_limit":
        if "max_power_kw" not in params:
            return "FAILED", "set_limit requires params.max_power_kw"
        state["limit_kw"] = max(0.0, min(float(params["max_power_kw"]), CAPACITY_KW))
        state["curtailed"] = state["limit_kw"] < CAPACITY_KW
        return "ACKED", None

    if ctype == "resume":
        state["limit_kw"] = CAPACITY_KW
        state["curtailed"] = False
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


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"solar-{DEVICE_ID}")
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(BROKER, 1883, 60)
client.loop_start()

while True:
    avail = available_kw()
    state["output_kw"] = round(min(avail, state["limit_kw"]), 2)

    telemetry = {
        "device_id": DEVICE_ID,
        "output_kw": state["output_kw"],
        "available_kw": avail,
        "limit_kw": state["limit_kw"],
        "curtailed": state["curtailed"],
        "capacity_kw": CAPACITY_KW,
    }
    client.publish(BASE_TOPIC, json.dumps(telemetry))
    print(f"[{DEVICE_ID}] telemetry {telemetry}")
    time.sleep(TELEMETRY_INTERVAL)
