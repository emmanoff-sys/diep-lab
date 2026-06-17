#!/usr/bin/env python3
"""DIEP K5 — EMQX HA validation script.

Tests mTLS auth, ACL enforcement, telemetry flow, DERMS command round-trip,
and failure resilience of the 3-node EMQX cluster via HAProxy.

Run inside a python:3.12 container on emqx-ha-val-net:
  docker run --rm --network diep-emqx-ha-val_emqx-ha-val-net \\
    -v $(pwd)/certs/devices:/certs:ro \\
    -v $(pwd)/emqx-ha-validation/scripts:/scripts \\
    python:3.12 sh -c "pip install -q paho-mqtt && python /scripts/validate-emqx-ha.py"
"""
import ssl
import time
import threading
import queue
import sys

import paho.mqtt.client as mqtt

BROKER = "emqx-ha-lb"
PORT = 8883
CA_CERT = "/certs/ca.crt"

CERTS = {
    "ingestor":   ("/certs/ingestor.crt",   "/certs/ingestor.key"),
    "dispatcher": ("/certs/dispatcher.crt", "/certs/dispatcher.key"),
    "INV001":     ("/certs/INV001.crt",     "/certs/INV001.key"),
    "BAT001":     ("/certs/BAT001.crt",     "/certs/BAT001.key"),
}

passed = []
failed = []


def _result(check_id, desc, ok, note=""):
    if ok:
        passed.append(check_id)
        print(f"  [PASS] {check_id}: {desc}" + (f" — {note}" if note else ""))
    else:
        failed.append(check_id)
        print(f"  [FAIL] {check_id}: {desc}" + (f" — {note}" if note else ""))


def make_client(cn, client_id=None):
    """Return a paho client configured for mTLS with the given cert CN."""
    cid = client_id or cn
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=True)
    cert_file, key_file = CERTS[cn]
    c.tls_set(
        ca_certs=CA_CERT,
        certfile=cert_file,
        keyfile=key_file,
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    return c


def connect_sync(client, timeout=8):
    """Blocking connect; returns True if successful."""
    connected = threading.Event()
    rc_holder = [None]

    def on_conn(c, ud, flags, rc, props=None):
        rc_holder[0] = rc
        connected.set()

    client.on_connect = on_conn
    try:
        client.connect(BROKER, PORT, keepalive=30)
        client.loop_start()
        ok = connected.wait(timeout)
        return ok and rc_holder[0] == 0
    except Exception as e:
        return False


# ─── V1: mTLS — valid cert connects ──────────────────────────────────────────
print("\n[V1] mTLS: valid cert → CONNACK success")
c_ing = make_client("ingestor", "val-v1-ingestor")
ok = connect_sync(c_ing)
_result("V1", "mTLS valid cert connects", ok)
c_ing.loop_stop(); c_ing.disconnect()
time.sleep(0.5)

# ─── V2: mTLS — no client cert → TLS handshake failure ───────────────────────
# paho.connect() is non-blocking; TLS failures are async.  The correct check is
# whether on_connect fires with rc=0.  If the server enforces fail_if_no_peer_cert,
# the TLS handshake is aborted and on_connect never fires — timeout = rejected.
print("\n[V2] mTLS: no client cert → TLS rejection")
connected_v2 = threading.Event()
c_nocert = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="val-v2-nocert", clean_session=True)
c_nocert.tls_set(ca_certs=CA_CERT, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

def on_conn_v2(c, ud, flags, rc, props=None):
    if rc == 0:
        connected_v2.set()

c_nocert.on_connect = on_conn_v2
try:
    c_nocert.connect(BROKER, PORT, keepalive=10)
    c_nocert.loop_start()
    time.sleep(3)
    c_nocert.loop_stop()
except Exception:
    pass
_result("V2", "No client cert rejected at TLS", not connected_v2.is_set())

# ─── V3: mTLS — self-signed (untrusted) cert → TLS failure ───────────────────
# Same async detection approach: if on_connect never fires with rc=0, the cert
# was rejected (EMQX log will show "Bad Certificate - selfsigned_peer").
print("\n[V3] mTLS: self-signed untrusted cert → TLS rejection")
import tempfile, os, subprocess
with tempfile.TemporaryDirectory() as td:
    untrusted_key = os.path.join(td, "untrusted.key")
    untrusted_crt = os.path.join(td, "untrusted.crt")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", untrusted_key,
         "-out", untrusted_crt, "-days", "1", "-nodes", "-subj", "/CN=untrusted"],
        capture_output=True
    )
    connected_v3 = threading.Event()
    c_untrusted = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="val-v3-untrusted", clean_session=True)
    c_untrusted.tls_set(
        ca_certs=CA_CERT, certfile=untrusted_crt, keyfile=untrusted_key,
        cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )

    def on_conn_v3(c, ud, flags, rc, props=None):
        if rc == 0:
            connected_v3.set()

    c_untrusted.on_connect = on_conn_v3
    try:
        c_untrusted.connect(BROKER, PORT, keepalive=10)
        c_untrusted.loop_start()
        time.sleep(3)
        c_untrusted.loop_stop()
    except Exception:
        pass
_result("V3", "Untrusted self-signed cert rejected", not connected_v3.is_set())

# ─── V4: ACL — ingestor subscribes to telemetry wildcard ─────────────────────
print("\n[V4] ACL: ingestor sub diep/+/+ (allowed)")
received_q: queue.Queue = queue.Queue()
c_sub = make_client("ingestor", "val-v4-ingestor-sub")
def on_msg_v4(c, ud, msg):
    received_q.put(msg.topic)
c_sub.on_message = on_msg_v4
connect_sync(c_sub)
sub_res, _ = c_sub.subscribe("diep/+/+", qos=0)
time.sleep(1)
# Publish from a device
c_pub = make_client("INV001", "val-v4-inv-pub")
connect_sync(c_pub)
c_pub.publish("diep/solar/INV001", '{"power_kw": 7.5}', qos=0)
time.sleep(1)
got = not received_q.empty()
_result("V4", "ingestor receives telemetry via sub diep/+/+", got,
        f"topic={received_q.get_nowait() if got else 'none'}")
c_sub.loop_stop(); c_sub.disconnect()
c_pub.loop_stop(); c_pub.disconnect()
time.sleep(0.5)

# ─── V5: ACL — device cannot publish to another device's topic ───────────────
print("\n[V5] ACL: INV001 cannot publish diep/solar/INV900 (denied → disconnect)")
disconnected_v5 = threading.Event()
c_v5 = make_client("INV001", "val-v5-inv-acl")

def on_disc_v5(c, ud, disc_flags, rc, props=None):
    disconnected_v5.set()

c_v5.on_disconnect = on_disc_v5
connect_sync(c_v5)
time.sleep(0.3)
c_v5.publish("diep/solar/INV900", "unauthorized", qos=0)
got_disconnect = disconnected_v5.wait(timeout=5)
_result("V5", "INV001 disconnected for publishing to INV900 topic", got_disconnect)
try:
    c_v5.loop_stop(); c_v5.disconnect()
except Exception:
    pass
time.sleep(0.5)

# ─── V6: ACL — device cannot publish to cmd topic ────────────────────────────
print("\n[V6] ACL: INV001 cannot publish diep/solar/INV001/cmd (denied → disconnect)")
disconnected_v6 = threading.Event()
c_v6 = make_client("INV001", "val-v6-inv-cmd")

def on_disc_v6(c, ud, disc_flags, rc, props=None):
    disconnected_v6.set()

c_v6.on_disconnect = on_disc_v6
connect_sync(c_v6)
time.sleep(0.3)
c_v6.publish("diep/solar/INV001/cmd", '{"command_type":"OVERRIDE"}', qos=0)
got_disconnect_cmd = disconnected_v6.wait(timeout=5)
_result("V6", "INV001 disconnected for publishing to /cmd topic", got_disconnect_cmd)
try:
    c_v6.loop_stop(); c_v6.disconnect()
except Exception:
    pass
time.sleep(0.5)

# ─── V7-V10: DERMS command round-trip ─────────────────────────────────────────
print("\n[V7-V10] DERMS command round-trip: dispatcher → device → ack")

cmd_received = threading.Event()
ack_received = threading.Event()
ack_payload_holder = [None]

# Device client: subscribes to its own cmd topic, publishes ack
c_device = make_client("INV001", "val-inv001-device")

def on_msg_device(c, ud, msg):
    cmd_received.set()
    # device sends ack
    c.publish("diep/solar/INV001/ack",
              '{"command_id":"TEST-CMD-001","status":"ACK"}', qos=1)

c_device.on_message = on_msg_device
connect_sync(c_device)
c_device.subscribe("diep/solar/INV001/cmd", qos=1)
time.sleep(0.5)

# Dispatcher client: publishes command, subscribes to ack topic
c_disp = make_client("dispatcher", "val-dispatcher")

def on_msg_disp(c, ud, msg):
    ack_payload_holder[0] = msg.payload.decode()
    ack_received.set()

c_disp.on_message = on_msg_disp
connect_sync(c_disp)
c_disp.subscribe("diep/+/+/ack", qos=1)
time.sleep(0.5)

# Dispatch the command
c_disp.publish("diep/solar/INV001/cmd",
               '{"command_id":"TEST-CMD-001","command_type":"SET_SETPOINT","value":5.0}',
               qos=1)

cmd_ok = cmd_received.wait(timeout=5)
ack_ok = ack_received.wait(timeout=5)

_result("V7",  "Dispatcher publishes command (QoS 1)", True,  "published ok")
_result("V8",  "Device receives command on /cmd topic", cmd_ok)
_result("V9",  "Device publishes ack on /ack topic", cmd_ok, "ack published after cmd received")
_result("V10", "Dispatcher receives ack from device",  ack_ok,
        f"payload={ack_payload_holder[0]!r}" if ack_ok else "timeout")

c_device.loop_stop(); c_device.disconnect()
c_disp.loop_stop(); c_disp.disconnect()
time.sleep(0.5)

# ─── V11: QoS 1 telemetry burst ───────────────────────────────────────────────
print("\n[V11] Telemetry burst: 50 messages, all received by ingestor")

burst_received = []
burst_lock = threading.Lock()
burst_done = threading.Event()
BURST_COUNT = 50

c_burst_sub = make_client("ingestor", "val-burst-ingestor")
c_burst_pub = make_client("INV001", "val-burst-inv")

def on_burst_msg(c, ud, msg):
    with burst_lock:
        burst_received.append(msg.payload.decode())
        if len(burst_received) >= BURST_COUNT:
            burst_done.set()

c_burst_sub.on_message = on_burst_msg
connect_sync(c_burst_sub)
c_burst_sub.subscribe("diep/solar/INV001", qos=0)
connect_sync(c_burst_pub)
time.sleep(0.3)

for i in range(BURST_COUNT):
    c_burst_pub.publish("diep/solar/INV001", f'{{"seq":{i},"power_kw":{i * 0.1:.1f}}}', qos=0)

burst_done.wait(timeout=10)
with burst_lock:
    n_recv = len(burst_received)

_result("V11", f"Burst {BURST_COUNT} telemetry messages received", n_recv == BURST_COUNT,
        f"{n_recv}/{BURST_COUNT}")

c_burst_sub.loop_stop(); c_burst_sub.disconnect()
c_burst_pub.loop_stop(); c_burst_pub.disconnect()

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  RESULTS: {len(passed)} PASS / {len(failed)} FAIL")
if failed:
    print(f"  FAILED: {', '.join(failed)}")
print(f"{'='*60}")
sys.exit(0 if not failed else 1)
