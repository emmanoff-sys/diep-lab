"""RC qualification Workstream 4: bounded soak load generator.

Continuous publish at a fixed sustainable rate for a long duration (minutes,
not seconds), no DB connection needed (matches sustained_test.py's
no-credential pattern) -- this script's only job is to keep realistic
traffic flowing while the qualification session observes memory/queue/WAL/
backup/alert behavior independently via docker stats, Prometheus, and
psql run directly against the diep-timescaledb container.

    docker run --rm --network diep-lab_diep-net \\
      -v <repo>/certs/devices:/certs:ro -v <worktree>:/app -w /app \\
      python:3.12 \\
      sh -c "pip install -q paho-mqtt && python3 validation/performance/soak_load.py <rate> <duration_s>"
"""
from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app")
from contracts import Measurement, Quality, TelemetryEnvelope  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402

DEVICE_ID = "SIT-METER-001"
TOPIC = "diep/smartmeter/METER001"
RATE = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
DURATION_S = float(sys.argv[2]) if len(sys.argv) > 2 else 1800.0


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"soak-{uuid.uuid4().hex[:8]}")
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


def main() -> None:
    client = connect_mqtt()
    time.sleep(1.0)
    print(f"=== Soak load: {RATE} msg/s for {DURATION_S}s, starting {datetime.now(timezone.utc).isoformat()} ===", flush=True)
    interval = 1.0 / RATE
    end = time.time() + DURATION_S
    seq = 1_000_000
    sent = 0
    next_report = time.time() + 60.0
    while time.time() < end:
        t0 = time.time()
        client.publish(TOPIC, make_envelope(seq).to_json(), qos=0)
        seq += 1
        sent += 1
        if t0 >= next_report:
            print(f"[{datetime.now(timezone.utc).isoformat()}] sent={sent}", flush=True)
            next_report = t0 + 60.0
        sleep_for = interval - (time.time() - t0)
        if sleep_for > 0:
            time.sleep(sleep_for)
    print(f"=== Soak load complete: sent={sent} at {datetime.now(timezone.utc).isoformat()} ===", flush=True)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
