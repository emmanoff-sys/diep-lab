"""RC qualification gap-fill: clean p50/p95/p99 latency AT the confirmed
~15 msg/s sustainable steady state.

PERFORMANCE_REPORT.md's own latency numbers are explicitly caveated as either
harness-artifact-tainted (1/10 msg/s tiers, batch-then-poll design records
early messages as "slow" only because polling hadn't started yet) or from an
overloaded/queueing state (100/1000+ msg/s tiers). Neither is real
steady-state per-message latency.

This script publishes continuously at a fixed rate while concurrently
polling for each message's arrival (poll runs in a background thread the
whole time, not after the publish phase ends), so latency reflects real
pipeline transit time, not measurement-window artifacts.

Invocation matches load_test.py's documented pattern:
    docker run --rm --network diep-lab_diep-net \\
      -v <repo>/certs/devices:/certs:ro -v <worktree>:/app -w /app \\
      --env-file .env -e DB_PASSWORD=<live-db-password> python:3.12 \\
      sh -c "pip install -q paho-mqtt psycopg2-binary && python3 validation/performance/steady_state_latency.py <rate> <duration_s>"
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app")
from contracts import Measurement, Quality, TelemetryEnvelope  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402
import psycopg2  # noqa: E402

DEVICE_ID = "SIT-METER-001"
TOPIC = "diep/smartmeter/METER001"
DB_HOST = os.getenv("DB_HOST", "diep-timescaledb")
DB_NAME = os.getenv("DB_NAME", "diep")
DB_USER = os.getenv("DB_USER", "diep")
DB_PASSWORD = os.environ["DB_PASSWORD"]

RATE = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
DURATION_S = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
POLL_INTERVAL_S = 0.5
DRAIN_GRACE_S = 30.0


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sit-steady-{uuid.uuid4().hex[:8]}")
    client.tls_set(ca_certs="/certs/ca.crt", certfile="/certs/METER001.crt", keyfile="/certs/METER001.key")
    client.connect("diep-mqtt", 8883, keepalive=60)
    client.loop_start()
    return client


def make_envelope(seq: int) -> tuple[str, TelemetryEnvelope]:
    cid = str(uuid.uuid4())
    return cid, TelemetryEnvelope(
        tenant_id="sit-tenant", site_id="SIT Validation Site", device_id=DEVICE_ID, meter_id=DEVICE_ID,
        timestamp_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        measurements=[Measurement(measurement_type="voltage", unit="V", value=230.0, quality=Quality.GOOD)],
        sequence_number=seq, correlation_id=cid,
    )


def main() -> None:
    client = connect_mqtt()
    time.sleep(1.0)
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    conn.autocommit = True

    pending: dict[str, float] = {}
    latencies: list[float] = []
    lock = threading.Lock()
    stop_polling = threading.Event()

    def poller() -> None:
        cur = conn.cursor()
        while not stop_polling.is_set():
            with lock:
                cids = list(pending.keys())
            if cids:
                cur.execute(
                    "SELECT metadata->>'correlation_id' FROM telemetry "
                    "WHERE device_id=%s AND time > now() - interval '10 minutes' "
                    "AND metadata->>'correlation_id' = ANY(%s)",
                    (DEVICE_ID, cids),
                )
                found = {row[0] for row in cur.fetchall()}
                now = time.time()
                with lock:
                    for cid in found:
                        sent_at = pending.pop(cid, None)
                        if sent_at is not None:
                            latencies.append(now - sent_at)
            time.sleep(POLL_INTERVAL_S)

    poll_thread = threading.Thread(target=poller, daemon=True)
    poll_thread.start()

    print(f"=== Steady-state latency: {RATE} msg/s for {DURATION_S}s (continuous publish+poll) ===")
    interval = 1.0 / RATE
    end = time.time() + DURATION_S
    seq = 900_000
    sent_count = 0
    while time.time() < end:
        t0 = time.time()
        cid, envelope = make_envelope(seq)
        client.publish(TOPIC, envelope.to_json(), qos=0)
        with lock:
            pending[cid] = t0
        seq += 1
        sent_count += 1
        sleep_for = interval - (time.time() - t0)
        if sleep_for > 0:
            time.sleep(sleep_for)

    print(f"Published {sent_count} messages over {DURATION_S}s. Waiting up to {DRAIN_GRACE_S}s for in-flight drain...")
    drain_deadline = time.time() + DRAIN_GRACE_S
    while time.time() < drain_deadline:
        with lock:
            remaining = len(pending)
        if remaining == 0:
            break
        time.sleep(1.0)

    stop_polling.set()
    poll_thread.join(timeout=5.0)

    with lock:
        never_observed = len(pending)

    if latencies:
        s = sorted(latencies)
        pct = {
            "p50": statistics.median(s),
            "p95": s[min(int(len(s) * 0.95), len(s) - 1)],
            "p99": s[min(int(len(s) * 0.99), len(s) - 1)],
            "min": s[0],
            "max": s[-1],
            "mean": statistics.mean(s),
        }
    else:
        pct = {}

    result = {
        "rate_msg_s": RATE,
        "duration_s": DURATION_S,
        "sent": sent_count,
        "observed": len(latencies),
        "never_observed_within_grace": never_observed,
        "latency_seconds": pct,
    }
    print("\n=== STEADY-STATE LATENCY RESULT (JSON) ===")
    print(json.dumps(result, indent=2))

    client.loop_stop()
    client.disconnect()
    conn.close()


if __name__ == "__main__":
    main()
