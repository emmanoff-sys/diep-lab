"""Round 2 — sustained-rate confirmatory test.

load_test.py's bursty 1/10/100/1000/2000/5000 msg/s tiers (back-to-back, 5s
each) proved the redesigned ingestor never permanently loses a message --
every received message eventually shows up in `ingestor_messages_persisted_total`
(confirmed: received == persisted, 0 "queue full" drops, 0 disconnects, even
at the 5000 msg/s burst). But because the tiers run back-to-back, an earlier
tier's undrained backlog bleeds into the next tier's measurement window, so
the "lost (never observed within timeout)" numbers there reflect the test's
polling timeout, not real loss -- not a useful "maximum sustainable rate"
figure on their own.

This script isolates one rate at a time, draining the queue fully via the
ingestor's own /health endpoint before *and* confirming full drain after,
to find the actual steady-state throughput ceiling of the full
ingestor -> FastAPI -> TimescaleDB path: the queue depth should stay flat
(input rate <= drain rate) at a sustainable rate, and grow throughout the
run at an unsustainable one.

Run the same way as load_test.py (see its docstring) -- this just needs the
extra ability to reach diep-ingestor:9203/health on the same network, which
docker-compose-ingestor.yml already exposes a port-mapped/aliased route for.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app")
from contracts import Measurement, Quality, TelemetryEnvelope  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402

DEVICE_ID = "SIT-METER-001"
TOPIC = "diep/smartmeter/METER001"
HEALTH_URL = "http://diep-ingestor:9203/health"

# Chosen from Round 2's burst-test drain-rate observation (~14-15 msg/s
# steady state) -- bracketing it to confirm the precise ceiling.
SUSTAINED_TIERS = (8, 12, 15, 18, 22, 30)
TIER_DURATION_S = 20.0


def queue_depth() -> int:
    with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
        return json.load(resp)["queue_depth"]


def wait_for_drain(timeout_s: float = 120.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if queue_depth() == 0:
            return True
        time.sleep(1)
    return False


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sit-sustained-{uuid.uuid4().hex[:8]}")
    client.tls_set(ca_certs="/certs/ca.crt", certfile="/certs/METER001.crt", keyfile="/certs/METER001.key")
    client.connect("diep-mqtt", 8883, keepalive=60)
    client.loop_start()
    return client


def make_envelope(seq: int) -> TelemetryEnvelope:
    return TelemetryEnvelope(
        tenant_id="sit-tenant", site_id="SIT Validation Site", device_id=DEVICE_ID, meter_id=DEVICE_ID,
        timestamp_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        measurements=[Measurement(measurement_type="voltage", unit="V", value=230.0, quality=Quality.GOOD)],
        sequence_number=seq, correlation_id=str(uuid.uuid4()),
    )


def run_tier(client: mqtt.Client, rate: float, duration_s: float, seq_start: int) -> tuple[int, list[int]]:
    interval = 1.0 / rate
    end = time.time() + duration_s
    seq = seq_start
    depths: list[int] = []
    next_sample = time.time()
    while time.time() < end:
        t0 = time.time()
        client.publish(TOPIC, make_envelope(seq).to_json(), qos=0)
        seq += 1
        if t0 >= next_sample:
            try:
                depths.append(queue_depth())
            except Exception:  # noqa: BLE001 -- a missed sample doesn't matter
                pass
            next_sample = t0 + 1.0
        sleep_for = interval - (time.time() - t0)
        if sleep_for > 0:
            time.sleep(sleep_for)
    return seq, depths


def main() -> None:
    client = connect_mqtt()
    time.sleep(1.0)
    if not wait_for_drain(30.0):
        print("WARNING: queue was not empty at start; results below may be skewed by leftover backlog")

    results = {}
    seq = 500_000
    for rate in SUSTAINED_TIERS:
        print(f"\n=== Sustained tier: {rate} msg/s for {TIER_DURATION_S}s (starting from drained queue) ===")
        seq, depths = run_tier(client, rate, TIER_DURATION_S, seq)
        drained = wait_for_drain(180.0)
        print(f"Queue depth samples during run: {depths}")
        print(f"Fully drained afterward (<=180s): {drained}")
        growing = len(depths) >= 2 and depths[-1] > depths[0] * 1.5
        results[rate] = {
            "rate_msg_s": rate,
            "depth_samples": depths,
            "max_depth_during_run": max(depths) if depths else None,
            "drained_after": drained,
            "queue_grew_during_run": growing,
        }
        time.sleep(2.0)

    print("\n=== SUSTAINED SUMMARY (JSON) ===")
    print(json.dumps(results, indent=2))

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
