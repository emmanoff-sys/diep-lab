import os
import time
import json
import random
import paho.mqtt.client as mqtt

broker = "mqtt"
topic = "diep/energy/meter1"

client = mqtt.Client()
client.username_pw_set(
    os.getenv("MQTT_USER", "diep-device"),
    os.getenv("MQTT_PASS", "device-pass-2026"),
)
client.connect(broker, 1883, 60)

battery_soc = 50.0

while True:

    # Simulated load demand
    load_kw = round(random.uniform(1.0, 5.0), 2)

    # Simulated solar production
    solar_kw = round(random.uniform(0.0, 10.0), 2)

    # Battery charging/discharging logic
    net_power = solar_kw - load_kw

    if net_power > 0:
        battery_soc += net_power * 0.1
    else:
        battery_soc += net_power * 0.05

    battery_soc = max(0, min(100, battery_soc))

    payload = {
        "voltage": round(random.uniform(220, 235), 2),
        "current": round(load_kw * 4, 2),
        "power_kw": load_kw,
        "frequency": round(random.uniform(49.8, 50.2), 2),
        "solar_kw": solar_kw,
        "battery_soc": round(battery_soc, 2),
        "grid_import_kw": max(0, load_kw - solar_kw),
        "grid_export_kw": max(0, solar_kw - load_kw)
    }

    client.publish(topic, json.dumps(payload))

    print(payload)

    time.sleep(5)


