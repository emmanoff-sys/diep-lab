"""DIEP microgrid controller simulator — bidirectional, site-level device.

A microgrid aggregates site generation/load and controls the exchange at the
point of common coupling (PCC) with the utility grid. It can run grid-connected
(the grid absorbs imbalance and holds frequency) or islanded (the microgrid must
self-balance; residual imbalance shows up as a frequency deviation via droop).

Participates in the command/control plane (see ev_charger.py for the pattern):
  - SUBSCRIBES to  diep/microgrid/<id>/cmd
  - PUBLISHES acks to diep/microgrid/<id>/ack
  - PUBLISHES telemetry to diep/microgrid/<id> every few seconds

Command vocabulary (must match ALLOWED_COMMANDS['microgrid'] in the API):
  island         params: {}                          # disconnect from utility grid
  grid_connect   params: {}                           # reconnect to utility grid
  set_setpoint   params: {"setpoint_kw": <float>}     # target PCC import(+)/export(-)
"""
import os
import time
import json
import random
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "mqtt")
MQTT_USER = os.getenv("MQTT_USER", "diep-device")
MQTT_PASS = os.getenv("MQTT_PASS", "device-pass-2026")
DEVICE_ID = os.getenv("DEVICE_ID", "MG001")
NOMINAL_FREQ = float(os.getenv("NOMINAL_FREQ", "50.0"))
# kW of net imbalance that shifts islanded frequency by 1 Hz (droop slope).
DROOP_KW_PER_HZ = float(os.getenv("DROOP_KW_PER_HZ", "20"))
TELEMETRY_INTERVAL = int(os.getenv("TELEMETRY_INTERVAL", "5"))

BASE_TOPIC = f"diep/microgrid/{DEVICE_ID}"
CMD_TOPIC = f"{BASE_TOPIC}/cmd"
ACK_TOPIC = f"{BASE_TOPIC}/ack"

state = {
    "grid_connected": True,
    "setpoint_kw": 0.0,   # desired PCC exchange when grid-connected
}


def apply_command(cmd):
    """Execute a command against microgrid state. Returns (status, error)."""
    ctype = cmd.get("command_type")
    params = cmd.get("params") or {}

    if ctype == "island":
        state["grid_connected"] = False
        return "ACKED", None

    if ctype == "grid_connect":
        state["grid_connected"] = True
        return "ACKED", None

    if ctype == "set_setpoint":
        if "setpoint_kw" not in params:
            return "FAILED", "set_setpoint requires params.setpoint_kw"
        state["setpoint_kw"] = float(params["setpoint_kw"])
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


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"microgrid-{DEVICE_ID}")
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(BROKER, 1883, 60)
client.loop_start()

while True:
    # Simulated instantaneous site balance.
    load_kw = round(random.uniform(5.0, 25.0), 2)
    solar_kw = round(random.uniform(0.0, 20.0), 2)
    net_load_kw = round(load_kw - solar_kw, 2)  # + = deficit, - = surplus

    if state["grid_connected"]:
        # Grid holds frequency and absorbs the difference; PCC tracks setpoint.
        pcc_kw = state["setpoint_kw"]
        frequency = round(NOMINAL_FREQ + random.uniform(-0.02, 0.02), 3)
    else:
        # Islanded: no grid exchange. Residual imbalance bends frequency (droop).
        pcc_kw = 0.0
        frequency = round(NOMINAL_FREQ - net_load_kw / DROOP_KW_PER_HZ, 3)

    telemetry = {
        "device_id": DEVICE_ID,
        "mode": "grid_connected" if state["grid_connected"] else "islanded",
        "grid_connected": state["grid_connected"],
        "setpoint_kw": state["setpoint_kw"],
        "pcc_kw": pcc_kw,
        "frequency": frequency,
        "load_kw": load_kw,
        "solar_kw": solar_kw,
        "net_load_kw": net_load_kw,
    }
    client.publish(BASE_TOPIC, json.dumps(telemetry))
    print(f"[{DEVICE_ID}] telemetry {telemetry}")
    time.sleep(TELEMETRY_INTERVAL)
