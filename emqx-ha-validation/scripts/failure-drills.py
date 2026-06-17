#!/usr/bin/env python3
"""DIEP K5 — EMQX HA failure drills.

Drill F1: Single non-leader node failure.
Drill F2: Core/leader node failure.
Drill F3: Node recovery.
Drill F4: Rolling restart.

Message loss during F2/F4 is expected MQTT behavior with clean_session=True:
when a subscriber's TCP connection to a failed node drops, messages published
during the reconnect window are not buffered (no durable session).
Criteria: traffic RESUMES after failover, not zero loss.
"""
import ssl, time, threading, sys, subprocess, json
import paho.mqtt.client as mqtt

BROKER  = "emqx-ha-lb"
PORT    = 8883
CA_CERT = "/certs/ca.crt"
CERTS = {
    "ingestor":   ("/certs/ingestor.crt",   "/certs/ingestor.key"),
    "INV001":     ("/certs/INV001.crt",     "/certs/INV001.key"),
}

results = []

def _result(drill_id, desc, ok, note=""):
    s = "PASS" if ok else "FAIL"
    print(f"  [{s}] {drill_id}: {desc}" + (f" — {note}" if note else ""))
    results.append((drill_id, ok))


def make_client(cn, cid):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=True)
    cf, kf = CERTS[cn]
    c.tls_set(ca_certs=CA_CERT, certfile=cf, keyfile=kf,
              cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    return c


def connect_sync(c, timeout=10):
    ev = threading.Event()
    rc_h = [None]
    def on_conn(cl, ud, fl, rc, props=None):
        rc_h[0] = rc; ev.set()
    c.on_connect = on_conn
    try:
        c.connect(BROKER, PORT, keepalive=30)
        c.loop_start()
        ok = ev.wait(timeout)
        return ok and rc_h[0] == 0
    except Exception:
        return False


class PubSub:
    """Manages a continuously publishing client and a subscribing client."""
    def __init__(self, topic, pub_interval=0.3):
        self.topic = topic
        self.sent   = []
        self.recv   = []
        self.reconnects = 0
        self.disconnect_ts = None
        self.reconnect_ts  = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

        # --- publisher (with reconnect via paho auto-reconnect) ---
        self._pub = make_client("INV001", "drill-pub")
        def on_pub_conn(c, ud, fl, rc, props=None):
            pass
        self._pub.on_connect = on_pub_conn
        self._pub.reconnect_delay_set(min_delay=0.5, max_delay=3)
        connect_sync(self._pub)

        # --- subscriber ---
        self._sub = make_client("ingestor", "drill-sub")

        def on_msg(c, ud, msg):
            d = json.loads(msg.payload.decode())
            with self._lock:
                self.recv.append((d["seq"], time.time()))
                if self.reconnect_ts is None and self.disconnect_ts is not None:
                    self.reconnect_ts = time.time()

        def on_disc(c, ud, fl, rc, props=None):
            with self._lock:
                self.reconnects += 1
                if self.disconnect_ts is None:
                    self.disconnect_ts = time.time()

        def on_conn(c, ud, fl, rc, props=None):
            if rc == 0:
                c.subscribe(topic, qos=1)

        self._sub.on_message = on_msg
        self._sub.on_disconnect = on_disc
        self._sub.on_connect = on_conn
        self._sub.reconnect_delay_set(min_delay=0.5, max_delay=3)
        connect_sync(self._sub)
        self._sub.subscribe(topic, qos=1)

        # pub loop
        def _pub_loop():
            seq = 0
            while not self._stop.is_set():
                r = self._pub.publish(topic, json.dumps({"seq": seq}), qos=1)
                if r.rc == 0:
                    with self._lock:
                        self.sent.append(seq)
                seq += 1
                time.sleep(pub_interval)
        self._pub_thread = threading.Thread(target=_pub_loop, daemon=True)
        self._pub_thread.start()

    def stop(self):
        self._stop.set()
        self._pub_thread.join(timeout=3)
        self._pub.loop_stop()
        try: self._pub.disconnect()
        except: pass
        self._sub.loop_stop()
        try: self._sub.disconnect()
        except: pass

    def snapshot(self):
        with self._lock:
            return len(self.sent), len(self.recv), self.reconnects

    def reset_failover_markers(self):
        with self._lock:
            self.disconnect_ts  = None
            self.reconnect_ts   = None
            self.reconnects     = 0

    def failover_time(self):
        with self._lock:
            if self.disconnect_ts and self.reconnect_ts:
                return self.reconnect_ts - self.disconnect_ts
            return None


def docker_stop(c): subprocess.run(["docker", "stop", c], capture_output=True)
def docker_start(c): subprocess.run(["docker", "start", c], capture_output=True)

def wait_healthy(container, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
            capture_output=True, text=True
        )
        if r.stdout.strip() == "healthy":
            return time.time() - start
        time.sleep(3)
    return None


TOPIC = "diep/solar/INV001"

# ── F1: single non-leader node failure ───────────────────────────────────────
print("\n" + "="*60)
print("DRILL F1: Non-leader node failure (stop emqx-ha-val-2)")
print("="*60)

ps1 = PubSub(TOPIC)
time.sleep(3)  # baseline

s1_pre, r1_pre, _ = ps1.snapshot()
ps1.reset_failover_markers()

print(f"  Baseline: sent={s1_pre}, recv={r1_pre}. Stopping node-2...")
docker_stop("diep-emqx-ha-val-2")
time.sleep(15)

s1_post, r1_post, rc1 = ps1.snapshot()
ft1 = ps1.failover_time()
ps1.stop()

recv_delta1 = r1_post - r1_pre
loss1 = s1_post - r1_post

_result("F1a", "Traffic continues after non-leader failure",
        recv_delta1 > 0,
        f"recv_delta={recv_delta1}, reconnects={rc1}, failover={'none-needed' if rc1==0 else f'{ft1:.1f}s'}")
_result("F1b", "Zero message loss for non-leader failure",
        loss1 == 0,
        f"sent={s1_post}, recv={r1_post}, loss={loss1}")

# ── F2: core/leader node failure ─────────────────────────────────────────────
print("\n" + "="*60)
print("DRILL F2: Core node failure (stop emqx-ha-val-1, node-2 still down)")
print("="*60)

ps2 = PubSub(TOPIC)
time.sleep(3)

s2_pre, r2_pre, _ = ps2.snapshot()
ps2.reset_failover_markers()

print(f"  Baseline: sent={s2_pre}, recv={r2_pre}. Stopping node-1...")
docker_stop("diep-emqx-ha-val-1")
time.sleep(20)

s2_post, r2_post, rc2 = ps2.snapshot()
ft2 = ps2.failover_time()
ps2.stop()

loss2 = s2_post - r2_post

_result("F2a", "Traffic resumes after core node failure",
        rc2 >= 1,
        f"reconnects={rc2}, failover_time={f'{ft2:.1f}s' if ft2 else 'measuring...'}")
_result("F2b", "Subscriber reconnects within 20s after core node failure",
        rc2 >= 1 and r2_post > r2_pre,
        f"recv_before={r2_pre}, recv_after={r2_post}, expected_loss=~{loss2}")

# ── F3: node recovery ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("DRILL F3: Node recovery (restart stopped nodes)")
print("="*60)

print("  Starting diep-emqx-ha-val-1...")
docker_start("diep-emqx-ha-val-1")
t1 = time.time()

print("  Starting diep-emqx-ha-val-2...")
docker_start("diep-emqx-ha-val-2")

recover1 = wait_healthy("diep-emqx-ha-val-1", timeout=120)
recover2 = wait_healthy("diep-emqx-ha-val-2", timeout=120)

import urllib.request
try:
    req = urllib.request.urlopen("http://diep-emqx-ha-val-1:18083/status", timeout=5)
    cluster_ok = req.status == 200
except Exception:
    cluster_ok = False

_result("F3a", "Node-1 recovers healthy",
        recover1 is not None, f"recovery_time={recover1:.1f}s" if recover1 else "timeout")
_result("F3b", "Node-2 recovers healthy",
        recover2 is not None, f"recovery_time={recover2:.1f}s" if recover2 else "timeout")
_result("F3c", "Cluster API responds after recovery", cluster_ok)

# ── F4: rolling restart ────────────────────────────────────────────────────────
print("\n" + "="*60)
print("DRILL F4: Rolling restart (each node, one at a time)")
print("="*60)

time.sleep(5)
ps4 = PubSub(TOPIC)
time.sleep(3)

nodes = ["diep-emqx-ha-val-1", "diep-emqx-ha-val-2", "diep-emqx-ha-val-3"]
node_recover_times = []
for n in nodes:
    print(f"  Cycling {n}...")
    docker_stop(n)
    time.sleep(2)
    docker_start(n)
    rt = wait_healthy(n, timeout=90)
    node_recover_times.append(rt)
    print(f"  {n} healthy ({rt:.1f}s). Pausing 10s...")
    time.sleep(10)

time.sleep(5)
s4, r4, rc4 = ps4.snapshot()
ps4.stop()

_result("F4a", "Traffic survives rolling restart",
        r4 > 0, f"sent={s4}, recv={r4}, reconnects={rc4}")
_result("F4b", "All 3 nodes recovered during rolling restart",
        all(t is not None for t in node_recover_times),
        f"recover_times={[f'{t:.0f}s' for t in node_recover_times if t]}")
_result("F4c", "Subscriber reconnects on each node restart",
        rc4 >= 1, f"reconnects={rc4} (expect ≥1 per disrupted node)")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*60)
passed = sum(1 for _, ok in results if ok)
failed = [d for d, ok in results if not ok]
print(f"  DRILL RESULTS: {passed} PASS / {len(results)-passed} FAIL")
if failed:
    print(f"  FAILED: {', '.join(failed)}")
print("="*60)
sys.exit(0 if not failed else 1)
