#!/usr/bin/env python3
"""Authoritative rebuild of the complete DIEP Node-RED flow.

Reconstructs config + telemetry + command nodes into one version-controlled
flows.json and deploys via the Admin API. Config and telemetry node defs are
transcribed from the original flow (captured during the platform review);
command node defs match nodered/inject_command_flow.py.

Telemetry: mqtt(diep/energy/meter1) -> json -> fn -> [influx 'smartmeter',
           3 dead-end alarm switches, debug, kafka 'energy.telemetry']
Command:   kafka diep.commands -> router -> mqtt cmd ; mqtt ack -> http -> FastAPI
"""
import json
import urllib.request

TAB = "f6f2187d.f17ca8"
MQTT_BROKER = "1864b5ccb5bd2f3d"
INFLUX_CFG = "430017b6c98e08eb"
KAFKA_CLIENT = "8b06075f973e4937"   # diep-kafka:9092 (used by consumer)
KAFKA_CLIENT_PROD = "b5fcd2e648e57890"  # diep-kafka:9092 (used by producer)


def kafka_client(node_id):
    return {
        "id": node_id, "type": "kafkajs-client", "name": "diep-kafka",
        "brokers": "diep-kafka:9092", "clientid": "diep-nodered",
        "connectiontimeout": 3000, "requesttimeout": 25000, "advancedretry": False,
        "maxretrytime": 30000, "initialretrytime": 300, "factor": 0.2, "multiplier": 2,
        "retries": 5, "auth": "none", "tlsselfsign": False, "tlscacert": "",
        "tlsclientcert": "", "tlsprivatekey": "", "tlspassphrase": "",
        "saslssl": True, "saslmechanism": "plain", "loglevel": "error",
    }


CMD_ROUTER_JS = (
    "var raw = (msg.payload && msg.payload.value !== undefined) ? msg.payload.value : msg.payload;\n"
    "var cmd;\n"
    "try { cmd = (typeof raw === 'string') ? JSON.parse(raw) : raw; }\n"
    "catch (e) { node.error('bad command json: ' + e.message, msg); return null; }\n"
    "var domainMap = { ev_charger: 'charger', battery: 'battery', solar_inverter: 'solar', microgrid: 'microgrid' };\n"
    "var domain = domainMap[cmd.device_type] || cmd.device_type;\n"
    "if (!cmd.device_id || !domain) { node.error('command missing device_id/device_type', msg); return null; }\n"
    "msg.topic = 'diep/' + domain + '/' + cmd.device_id + '/cmd';\n"
    "msg.payload = JSON.stringify(cmd);\n"
    "node.status({ fill: 'blue', shape: 'dot', text: cmd.command_type + ' -> ' + cmd.device_id });\n"
    "return msg;"
)

ACK_ROUTER_JS = (
    "var ack = msg.payload;\n"
    "if (typeof ack === 'string') { try { ack = JSON.parse(ack); } catch (e) { node.error('bad ack json', msg); return null; } }\n"
    "if (!ack || !ack.command_id) { node.error('ack missing command_id', msg); return null; }\n"
    "msg.method = 'POST';\n"
    "msg.url = 'http://diep-fastapi:8000/commands/' + ack.command_id + '/ack';\n"
    "msg.headers = { 'content-type': 'application/json' };\n"
    "msg.payload = { status: ack.status, error: ack.error || null };\n"
    "node.status({ fill: 'green', shape: 'dot', text: ack.status + ' ' + ack.command_id });\n"
    "return msg;"
)

FLOWS = [
    {"id": TAB, "type": "tab", "label": "Flow 1", "disabled": False, "info": ""},

    # --- config nodes ---
    {"id": MQTT_BROKER, "type": "mqtt-broker", "name": "", "broker": "mqtt", "port": 1883,
     "clientid": "", "autoConnect": True, "usetls": False, "protocolVersion": 4,
     "keepalive": 60, "cleansession": True, "autoUnsubscribe": True,
     "birthTopic": "", "birthQos": "0", "birthRetain": "false", "birthPayload": "", "birthMsg": {},
     "closeTopic": "", "closeQos": "0", "closeRetain": "false", "closePayload": "", "closeMsg": {},
     "willTopic": "", "willQos": "0", "willRetain": "false", "willPayload": "", "willMsg": {},
     "userProps": "", "sessionExpiry": "",
     # Deployed to Node-RED's encrypted credential store; stripped from the repo copy.
     "credentials": {"user": "diep-nodered", "password": "nodered-pass-2026"}},
    {"id": INFLUX_CFG, "type": "influxdb", "hostname": "influxdb", "port": 8086,
     "protocol": "http", "database": "energy", "name": "", "usetls": False, "tls": "",
     "influxdbVersion": "1.x", "url": "http://localhost:8086", "timeout": 10,
     "rejectUnauthorized": True},
    kafka_client(KAFKA_CLIENT),
    kafka_client(KAFKA_CLIENT_PROD),

    # --- telemetry path ---
    {"id": "bf8d805dca5dff7d", "type": "mqtt in", "z": TAB, "name": "", "topic": "diep/energy/meter1",
     "qos": "2", "datatype": "auto-detect", "broker": MQTT_BROKER, "nl": False, "rap": True, "rh": 0,
     "inputs": 0, "x": 230, "y": 380, "wires": [["58c4d2d859f1177b"]]},
    {"id": "58c4d2d859f1177b", "type": "json", "z": TAB, "name": "", "property": "payload",
     "action": "obj", "pretty": False, "x": 370, "y": 460, "wires": [["5b69382969dd3cc2"]]},
    {"id": "5b69382969dd3cc2", "type": "function", "z": TAB, "name": "function 1",
     "func": "msg.payload = { device_id: 'METER001', voltage: msg.payload.voltage, current: msg.payload.current, power_kw: msg.payload.power_kw, frequency: msg.payload.frequency, solar_kw: msg.payload.solar_kw, battery_soc: msg.payload.battery_soc, grid_import_kw: msg.payload.grid_import_kw, grid_export_kw: msg.payload.grid_export_kw }; return msg;",
     "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 520, "y": 540,
     "wires": [["56aa105d14476f03", "e56e25010828ac84", "333846a90b139664",
                "34ff0e2f1cd02ff9", "047f7e9fa5571c4f", "7ffd90e476c8679f", "telemetry_router"]]},
    {"id": "56aa105d14476f03", "type": "influxdb out", "z": TAB, "influxdb": INFLUX_CFG,
     "name": "", "measurement": "smartmeter", "precision": "", "retentionPolicy": "",
     "database": "energy", "precisionV18FluxV20": "ms", "retentionPolicyV18Flux": "",
     "org": "organisation", "bucket": "bucket", "x": 790, "y": 460, "wires": []},
    {"id": "e56e25010828ac84", "type": "switch", "z": TAB, "name": "Battery Low Alarm",
     "property": "payload.battery_soc", "propertyType": "msg", "rules": [{"t": "lt", "v": "20", "vt": "num"}],
     "checkall": "true", "repair": False, "outputs": 1, "x": 800, "y": 520, "wires": [[]]},
    {"id": "333846a90b139664", "type": "switch", "z": TAB, "name": "Voltage Alarm",
     "property": "payload.voltage", "propertyType": "msg",
     "rules": [{"t": "lt", "v": "210", "vt": "num"}, {"t": "gt", "v": "240", "vt": "num"}],
     "checkall": "true", "repair": False, "outputs": 2, "x": 800, "y": 580, "wires": [[], []]},
    {"id": "34ff0e2f1cd02ff9", "type": "switch", "z": TAB, "name": "Frequency Alarm",
     "property": "payload.frequency", "propertyType": "msg",
     "rules": [{"t": "lt", "v": "49.5", "vt": "num"}, {"t": "gt", "v": "49.8", "vt": "num"}],
     "checkall": "true", "repair": False, "outputs": 2, "x": 800, "y": 640, "wires": [[], []]},
    {"id": "047f7e9fa5571c4f", "type": "debug", "z": TAB, "name": "", "active": True,
     "tosidebar": True, "console": False, "tostatus": False, "complete": "payload",
     "targetType": "msg", "statusVal": "", "statusType": "auto", "x": 790, "y": 700, "wires": []},
    {"id": "7ffd90e476c8679f", "type": "function", "z": TAB, "name": "Kafka Formatter",
     "func": "msg.payload = JSON.stringify(msg.payload); return msg;", "outputs": 1,
     "timeout": 0, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 800, "y": 460, "wires": [["19773179c026876a"]]},
    {"id": "telemetry_router", "type": "function", "z": TAB, "name": "telemetry -> FastAPI",
     "func": "msg.method = 'POST'; msg.url = 'http://diep-fastapi:8000/telemetry'; msg.headers = {'content-type': 'application/json'}; return msg;",
     "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 800, "y": 760, "wires": [["telemetry_http"]]},
    {"id": "telemetry_http", "type": "http request", "z": TAB, "name": "POST /telemetry",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "insecureHTTPParser": False, "authType": "", "senderr": False,
     "headers": [], "x": 1040, "y": 760, "wires": [[]]},
    {"id": "56aa105d14476f03", "type": "influxdb out", "z": TAB, "influxdb": INFLUX_CFG,
     "name": "", "measurement": "smartmeter", "precision": "", "retentionPolicy": "",
     "database": "energy", "precisionV18FluxV20": "ms", "retentionPolicyV18Flux": "",
     "org": "organisation", "bucket": "bucket", "x": 790, "y": 460, "wires": []},
    {"id": "e56e25010828ac84", "type": "switch", "z": TAB, "name": "Battery Low Alarm",
     "property": "payload.battery_soc", "propertyType": "msg", "rules": [{"t": "lt", "v": "20", "vt": "num"}],
     "checkall": "true", "repair": False, "outputs": 1, "x": 800, "y": 520, "wires": [[]]},
    {"id": "333846a90b139664", "type": "switch", "z": TAB, "name": "Voltage Alarm",
     "property": "payload.voltage", "propertyType": "msg",
     "rules": [{"t": "lt", "v": "210", "vt": "num"}, {"t": "gt", "v": "240", "vt": "num"}],
     "checkall": "true", "repair": False, "outputs": 2, "x": 800, "y": 580, "wires": [[], []]},
    {"id": "34ff0e2f1cd02ff9", "type": "switch", "z": TAB, "name": "Frequency Alarm",
     "property": "payload.frequency", "propertyType": "msg",
     "rules": [{"t": "lt", "v": "49.5", "vt": "num"}, {"t": "gt", "v": "49.8", "vt": "num"}],
     "checkall": "true", "repair": False, "outputs": 2, "x": 800, "y": 640, "wires": [[], []]},
    {"id": "047f7e9fa5571c4f", "type": "debug", "z": TAB, "name": "", "active": True,
     "tosidebar": True, "console": False, "tostatus": False, "complete": "payload",
     "targetType": "msg", "statusVal": "", "statusType": "auto", "x": 790, "y": 700, "wires": []},
    {"id": "7ffd90e476c8679f", "type": "function", "z": TAB, "name": "Kafka Formatter",
     "func": "msg.payload = JSON.stringify(msg.payload); return msg;", "outputs": 1,
     "timeout": 0, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 800, "y": 460, "wires": [["19773179c026876a"]]},
    {"id": "19773179c026876a", "type": "kafkajs-producer", "z": TAB,
     "name": "energy-telemetry-producer", "client": KAFKA_CLIENT_PROD, "topic": "energy.telemetry",
     "advancedoptions": False, "acknowledge": "all", "partition": "", "headeritems": {},
     "key": "", "responsetimeout": 30000, "transactiontimeout": 60000,
     "metadatamaxage": 300000, "allowautotopiccreation": False, "x": 1000, "y": 460, "wires": []},

    # --- command path ---
    {"id": "diep_cmd_consumer", "type": "kafkajs-consumer", "z": TAB,
     "name": "diep.commands consumer", "client": KAFKA_CLIENT,
     "groupid": "diep-command-dispatcher", "topic": "diep.commands",
     "advancedoptions": False, "autocommitinterval": "", "autocommitthreshold": "",
     "sessiontimeout": "", "rebalancetimeout": "", "heartbeatinterval": "",
     "metadatamaxage": "", "maxbytesperpartition": "", "minbytes": "", "maxbytes": "",
     "maxwaittimeinms": "", "allowautotopiccreation": False, "clearoffsets": False,
     "frombeginning": False, "x": 240, "y": 800, "wires": [["diep_cmd_router"]]},
    {"id": "diep_cmd_router", "type": "function", "z": TAB, "name": "command router",
     "func": CMD_ROUTER_JS, "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "",
     "finalize": "", "libs": [], "x": 480, "y": 800, "wires": [["diep_cmd_mqtt_out"]]},
    {"id": "diep_cmd_mqtt_out", "type": "mqtt out", "z": TAB, "name": "device cmd",
     "topic": "", "qos": "1", "retain": "false", "respTopic": "", "contentType": "",
     "userProps": "", "correl": "", "expiry": "", "broker": MQTT_BROKER,
     "x": 720, "y": 800, "wires": []},
    {"id": "diep_ack_mqtt_in", "type": "mqtt in", "z": TAB, "name": "device ack",
     "topic": "diep/+/+/ack", "qos": "1", "datatype": "auto-detect", "broker": MQTT_BROKER,
     "nl": False, "rap": True, "rh": 0, "inputs": 0, "x": 240, "y": 880,
     "wires": [["diep_ack_router"]]},
    {"id": "diep_ack_router", "type": "function", "z": TAB, "name": "ack -> FastAPI",
     "func": ACK_ROUTER_JS, "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "",
     "finalize": "", "libs": [], "x": 480, "y": 880, "wires": [["diep_ack_http"]]},
    {"id": "diep_ack_http", "type": "http request", "z": TAB, "name": "POST /commands/{id}/ack",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "", "persist": False,
     "proxy": "", "insecureHTTPParser": False, "authType": "", "senderr": False, "headers": [],
     "x": 760, "y": 880, "wires": [[]]},
]


def main():
    body = json.dumps(FLOWS).encode()
    req = urllib.request.Request(
        "http://localhost:1880/flows", data=body, method="POST",
        headers={"Content-Type": "application/json", "Node-RED-Deployment-Type": "full"})
    print("deploy status:", urllib.request.urlopen(req).status)
    # Strip secrets from the version-controlled copy.
    sanitized = [{k: v for k, v in n.items() if k != "credentials"} for n in FLOWS]
    with open("/home/emmanuel/diep-lab/nodered/flows.json", "w") as f:
        json.dump(sanitized, f, indent=2)
    print(f"wrote repo copy: {len(sanitized)} nodes (credentials stripped)")


if __name__ == "__main__":
    main()
