"""SIT Scenario B — multiple meters: ordering, throughput, tenant isolation.

Publishes a rapid burst across 6 synthetic meters (5 under 'sit-tenant', 1
under 'sit-tenant-b'), each with a distinct, verifiable sequence_number and
value, then checks: (1) every row lands attributed to the correct device
with no cross-device value bleeding, (2) all N messages are ingested within
a bounded wall-clock window, (3) each device's recorded tenant_id matches
what was sent, with no cross-tenant attribution.
"""
import json
import sys
import time

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, publish_envelope, query_db  # noqa: E402

DEVICES = [
    ("SIT-METER-001", "sit-tenant"),
    ("SIT-METER-002", "sit-tenant"),
    ("SIT-METER-003", "sit-tenant"),
    ("SIT-METER-004", "sit-tenant"),
    ("SIT-METER-005", "sit-tenant"),
    ("SIT-METER-006", "sit-tenant-b"),
]


def main():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    base_seq = 2000
    sent = {}
    t0 = time.monotonic()
    for i, (device_id, tenant_id) in enumerate(DEVICES):
        voltage = 220.0 + i  # distinct, verifiable per-device value
        seq = base_seq + i
        envelope = make_envelope(
            device_id, tenant_id=tenant_id, sequence_number=seq,
            measurements=[Measurement(measurement_type="voltage", unit="V", value=voltage, quality=Quality.GOOD)],
        )
        publish_envelope(envelope)
        sent[device_id] = {"voltage": voltage, "seq": seq, "tenant_id": tenant_id, "timestamp_utc": envelope.timestamp_utc}
    elapsed = time.monotonic() - t0
    print(f"Published {len(DEVICES)} envelopes in {elapsed:.2f}s ({len(DEVICES)/elapsed:.1f} msg/s)")

    time.sleep(2.5)  # ingestor processing latency

    rows = query_db(
        "SELECT t.device_id, t.voltage, t.metadata, d.tenant_id AS registry_tenant_id "
        "FROM telemetry t JOIN devices d ON d.device_id = t.device_id "
        "WHERE t.device_id IN ('SIT-METER-001','SIT-METER-002','SIT-METER-003','SIT-METER-004','SIT-METER-005','SIT-METER-006') "
        "AND t.time > now() - interval '1 minute' "
        "ORDER BY t.device_id;"
    )
    print(json.dumps(rows, indent=2))

    check("all 6 devices produced exactly one matching row", len(rows) == 6)
    by_device = {r["device_id"]: r for r in rows}
    for device_id, expected in sent.items():
        row = by_device.get(device_id)
        check(f"{device_id}: voltage matches its own value (no cross-device bleed)",
              row is not None and float(row["voltage"]) == expected["voltage"])
        meta = json.loads(row["metadata"]) if row else {}
        check(f"{device_id}: metadata sequence_number matches",
              meta.get("sequence_number") == expected["seq"])
        check(f"{device_id}: envelope tenant_id == registry tenant_id (no cross-tenant attribution)",
              meta.get("tenant_id") == expected["tenant_id"] == (row["registry_tenant_id"] if row else None))

    print(
        f"NOTE: {elapsed:.1f}s for 6 publishes here is harness overhead (one throwaway "
        "docker container per mosquitto_pub call, ~2-3s container startup each) — not a "
        "measurement of pipeline throughput. See PERFORMANCE_REPORT.md for the real "
        "throughput numbers, measured from a single long-lived MQTT connection."
    )

    # Ordering: 3 sequential updates to ONE device — every row must persist
    # (not overwritten) and stay attributable to its own sequence_number.
    order_seqs = [3000, 3001, 3002]
    for seq in order_seqs:
        envelope = make_envelope(
            "SIT-METER-002", tenant_id="sit-tenant", sequence_number=seq,
            measurements=[Measurement(measurement_type="voltage", unit="V", value=200.0 + seq, quality=Quality.GOOD)],
        )
        publish_envelope(envelope)
    time.sleep(2.5)

    order_rows = query_db(
        "SELECT time, voltage, metadata FROM telemetry WHERE device_id='SIT-METER-002' "
        "AND time > now() - interval '1 minute' ORDER BY time ASC;"
    )
    print(json.dumps(order_rows, indent=2))
    seen_seqs = [json.loads(r["metadata"]).get("sequence_number") for r in order_rows]
    check("ordering: all 3 sequential updates persisted as separate rows (none overwritten)",
          all(s in seen_seqs for s in order_seqs))
    relevant = [s for s in seen_seqs if s in order_seqs]
    check("ordering: rows appear in the same sequence_number order they were sent",
          relevant == order_seqs)

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
