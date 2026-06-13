#!/usr/bin/env python3
"""Inject the DIEP command/control flow into the running Node-RED instance.

Adds, on the existing "Flow 1" tab, two chains:
  1. diep.commands (Kafka) -> router -> MQTT diep/<domain>/<id>/cmd
  2. MQTT diep/+/+/ack    -> router -> HTTP POST FastAPI /commands/{id}/ack

Reuses existing config nodes:
  - kafkajs-client  8b06075f973e4937  (brokers diep-kafka:9092)
  - mqtt-broker     1864b5ccb5bd2f3d  (broker host 'mqtt':1883)

Idempotent: nodes are keyed by stable ids and replaced on re-run.
"""
import json
import sys
import urllib.request

NODERED = "http://localhost:1880/flows"
TAB = "f6f2187d.f17ca8"
KAFKA_CLIENT = "8b06075f973e4937"
MQTT_BROKER = "1864b5ccb5bd2f3d"

COMMAND_ROUTER_JS = """
// kafkajs-consumer emits the message value as a string in msg.payload.value
var raw = (msg.payload && msg.payload.value !== undefined) ? msg.payload.value : msg.payload;
var cmd;
try { cmd = (typeof raw === 'string') ? JSON.parse(raw) : raw; }
catch (e) { node.error('bad command json: ' + e.message, msg); return null; }

var domainMap = { ev_charger: 'charger', battery: 'battery', solar_inverter: 'solar', microgrid: 'microgrid' };
var domain = domainMap[cmd.device_type] || cmd.device_type;
if (!cmd.device_id || !domain) { node.error('command missing device_id/device_type', msg); return null; }

msg.topic = 'diep/' + domain + '/' + cmd.device_id + '/cmd';
msg.payload = JSON.stringify(cmd);
node.status({ fill: 'blue', shape: 'dot', text: cmd.command_type + ' -> ' + cmd.device_id });
return msg;
""".strip()

ACK_ROUTER_JS = """
var ack = msg.payload;
if (typeof ack === 'string') { try { ack = JSON.parse(ack); } catch (e) { node.error('bad ack json', msg); return null; } }
if (!ack || !ack.command_id) { node.error('ack missing command_id', msg); return null; }
msg.method = 'POST';
msg.url = 'http://diep-fastapi:8000/commands/' + ack.command_id + '/ack';
msg.headers = { 'content-type': 'application/json' };
msg.payload = { status: ack.status, error: ack.error || null };
node.status({ fill: 'green', shape: 'dot', text: ack.status + ' ' + ack.command_id });
return msg;
""".strip()

NEW_NODES = [
    {
        "id": "diep_cmd_consumer", "type": "kafkajs-consumer", "z": TAB,
        "name": "diep.commands consumer", "client": KAFKA_CLIENT,
        "groupid": "diep-command-dispatcher", "topic": "diep.commands",
        "advancedoptions": False, "autocommitinterval": "", "autocommitthreshold": "",
        "sessiontimeout": "", "rebalancetimeout": "", "heartbeatinterval": "",
        "metadatamaxage": "", "maxbytesperpartition": "", "minbytes": "",
        "maxbytes": "", "maxwaittimeinms": "", "allowautotopiccreation": False,
        "clearoffsets": False, "frombeginning": False,
        "x": 240, "y": 700, "wires": [["diep_cmd_router"]],
    },
    {
        "id": "diep_cmd_router", "type": "function", "z": TAB,
        "name": "command router", "func": COMMAND_ROUTER_JS, "outputs": 1,
        "timeout": 0, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
        "x": 480, "y": 700, "wires": [["diep_cmd_mqtt_out"]],
    },
    {
        "id": "diep_cmd_mqtt_out", "type": "mqtt out", "z": TAB,
        "name": "device cmd", "topic": "", "qos": "1", "retain": "false",
        "respTopic": "", "contentType": "", "userProps": "", "correl": "",
        "expiry": "", "broker": MQTT_BROKER,
        "x": 720, "y": 700, "wires": [],
    },
    {
        "id": "diep_ack_mqtt_in", "type": "mqtt in", "z": TAB,
        "name": "device ack", "topic": "diep/+/+/ack", "qos": "1",
        "datatype": "auto-detect", "broker": MQTT_BROKER,
        "nl": False, "rap": True, "rh": 0, "inputs": 0,
        "x": 240, "y": 800, "wires": [["diep_ack_router"]],
    },
    {
        "id": "diep_ack_router", "type": "function", "z": TAB,
        "name": "ack -> FastAPI", "func": ACK_ROUTER_JS, "outputs": 1,
        "timeout": 0, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
        "x": 480, "y": 800, "wires": [["diep_ack_http"]],
    },
    {
        "id": "diep_ack_http", "type": "http request", "z": TAB,
        "name": "POST /commands/{id}/ack", "method": "use", "ret": "obj",
        "paytoqs": "ignore", "url": "", "tls": "", "persist": False, "proxy": "",
        "insecureHTTPParser": False, "authType": "", "senderr": False, "headers": [],
        "x": 760, "y": 800, "wires": [[]],
    },
]

NEW_IDS = {n["id"] for n in NEW_NODES}


def main():
    cur = json.load(urllib.request.urlopen(NODERED))
    # Drop any prior copies of our nodes so re-running is idempotent.
    merged = [n for n in cur if n.get("id") not in NEW_IDS] + NEW_NODES

    body = json.dumps(merged).encode()
    req = urllib.request.Request(
        NODERED, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Node-RED-Deployment-Type": "full"},
    )
    resp = urllib.request.urlopen(req)
    print(f"deploy status: {resp.status}")

    # Persist the deployed flows into the repo for version control.
    with open("/home/emmanuel/diep-lab/nodered/flows.json", "w") as f:
        json.dump(merged, f, indent=2)
    print(f"wrote repo copy: {len(merged)} nodes")


if __name__ == "__main__":
    sys.exit(main())
