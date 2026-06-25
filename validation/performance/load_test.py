"""SIT Performance Validation — end-to-end latency (P50/P95/P99/max) and
throughput at 1/10/100/1000 msg/s against the REAL, live ingestor -> FastAPI
-> TimescaleDB path (the only path that's actually wired end-to-end; see
INTEGRATION_VALIDATION_REPORT.md for why MDM/OPC UA are out of scope here).

Runs as a single long-lived process (one MQTT connection, one DB
connection) so per-message overhead is the pipeline's own, not container
spin-up cost (see Scenario B's note on why a container-per-message harness
distorts latency/throughput numbers). Intended to run via:

    docker run --rm --network diep-lab_diep-net \\
      -v <repo>/certs/devices:/certs:ro -v <worktree>:/app -w /app \\
      --env-file .env python:3.12 \\
      sh -c "pip install -q paho-mqtt psycopg2-binary && python3 validation/performance/load_test.py"
"""
from __future__ import annotations

import json
import os
import statistics
import sys
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


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sit-loadtest-{uuid.uuid4().hex[:8]}")
    client.tls_set(ca_certs="/certs/ca.crt", certfile="/certs/METER001.crt", keyfile="/certs/METER001.key")
    client.connect("diep-mqtt", 8883, keepalive=60)
    client.loop_start()
    return client


def connect_db():
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)


def make_envelope(seq: int) -> TelemetryEnvelope:
    return TelemetryEnvelope(
        tenant_id="sit-tenant", site_id="SIT Validation Site", device_id=DEVICE_ID, meter_id=DEVICE_ID,
        timestamp_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        measurements=[Measurement(measurement_type="voltage", unit="V", value=230.0, quality=Quality.GOOD)],
        sequence_number=seq, correlation_id=str(uuid.uuid4()),
    )


def publish_burst(client: mqtt.Client, rate: float, duration_s: float, seq_start: int) -> list[tuple[str, float]]:
    sent = []
    interval = 1.0 / rate
    end = time.time() + duration_s
    seq = seq_start
    while time.time() < end:
        t0 = time.time()
        envelope = make_envelope(seq)
        client.publish(TOPIC, envelope.to_json(), qos=0)
        sent.append((envelope.correlation_id, t0))
        seq += 1
        sleep_for = interval - (time.time() - t0)
        if sleep_for > 0:
            time.sleep(sleep_for)
    return sent


def measure_latencies(conn, sent: list[tuple[str, float]], timeout_s: float = 30.0):
    pending = dict(sent)
    latencies = []
    cur = conn.cursor()
    deadline = time.time() + timeout_s
    while pending and time.time() < deadline:
        cur.execute(
            "SELECT metadata->>'correlation_id' FROM telemetry "
            "WHERE device_id=%s AND time > now() - interval '5 minutes'",
            (DEVICE_ID,),
        )
        found = {row[0] for row in cur.fetchall()}
        now = time.time()
        for cid in list(pending):
            if cid in found:
                latencies.append(now - pending.pop(cid))
        if pending:
            time.sleep(0.1)
    return latencies, len(pending)


def percentiles(values: list[float]) -> dict:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "max": None, "min": None, "mean": None}
    s = sorted(values)
    return {
        "p50": statistics.median(s),
        "p95": s[min(int(len(s) * 0.95), len(s) - 1)],
        "p99": s[min(int(len(s) * 0.99), len(s) - 1)],
        "max": s[-1],
        "min": s[0],
        "mean": statistics.mean(s),
    }


# Round 2 (post-stabilization): the original 1/10/100/1000 tiers stay for an
# apples-to-apples delta against PERFORMANCE_REPORT.md's baseline; 2000/5000
# are new, specifically to find the redesigned ingestor's new ceiling (the
# original ceiling was ~90 msg/s clean, well below even the old "1000" tier).
TIERS = (1, 10, 100, 1000, 2000, 5000)


def main():
    mqtt_client = connect_mqtt()
    time.sleep(1.0)  # let the connection establish before the first burst
    db_conn = connect_db()

    results = {}
    seq = 100000
    for rate in TIERS:
        duration = 5.0
        print(f"\n=== Tier: {rate} msg/s for {duration}s ===")
        tier_start = datetime.now(timezone.utc).isoformat()
        t0 = time.time()
        sent = publish_burst(mqtt_client, rate, duration, seq)
        publish_elapsed = time.time() - t0
        seq += len(sent)
        actual_rate = len(sent) / publish_elapsed
        print(f"Published {len(sent)} messages in {publish_elapsed:.2f}s (actual rate achieved: {actual_rate:.1f} msg/s)")

        latencies, lost = measure_latencies(db_conn, sent, timeout_s=max(30.0, duration * 4, rate / 50))
        tier_end = datetime.now(timezone.utc).isoformat()
        pct = percentiles(latencies)
        delivered = len(sent) - lost
        print(f"Delivered to DB: {delivered}/{len(sent)} (lost/never observed within timeout: {lost})")
        print(f"Latency (s): p50={pct['p50']}, p95={pct['p95']}, p99={pct['p99']}, max={pct['max']}, mean={pct['mean']}")
        print(f"Tier window (UTC): {tier_start} -> {tier_end}")  # for correlating CPU/mem samples after the fact

        results[rate] = {
            "requested_rate_msg_s": rate,
            "actual_publish_rate_msg_s": actual_rate,
            "sent": len(sent),
            "delivered": delivered,
            "lost": lost,
            "latency_seconds": pct,
            "tier_start_utc": tier_start,
            "tier_end_utc": tier_end,
        }
        time.sleep(2.0)  # let the pipeline drain before the next tier

    print("\n=== SUMMARY (JSON) ===")
    print(json.dumps(results, indent=2, default=str))

    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    db_conn.close()


if __name__ == "__main__":
    main()
