"""SIT Scenario G (new, post-stabilization sprint, Work Item 5/6) — the OPC
UA connector's MDM trusted-stream consumer (services/opcua/mdm_consumer.py).

Publishes a raw envelope through the real pipeline (AMI -> MDM -> trusted
topic) and reads it back from the OPC UA connector's own /health endpoint
(http://localhost:9202/health, loopback-only per docker-compose-opcua.yml),
checking the three things Work Item 5 named explicitly: quality
propagation, timestamp propagation, metadata propagation. Reconnect/
subscription behavior is covered by services/opcua's existing test suite
(60/60, see VALIDATION.md) plus this consumer's own live MQTT reconnect
logic, exercised the same way ingestor/MDM's is (real broker, not a fake).
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, publish_envelope  # noqa: E402

OPCUA_HEALTH_URL = "http://localhost:9202/health"
DEVICE_ID = "SIT-METER-006"  # sit-tenant-b, shares SIT-FDR-01/SIT-TX-01 with sit-tenant


def opcua_health() -> dict:
    with urllib.request.urlopen(OPCUA_HEALTH_URL, timeout=5) as resp:
        return json.load(resp)


def main():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    # --- Case 1: a clean GOOD reading -- quality/timestamp/metadata propagation ---
    envelope = make_envelope(
        DEVICE_ID, tenant_id="sit-tenant-b", sequence_number=9300,
        measurements=[Measurement(measurement_type="power_kw", unit="kW", value=17.25, quality=Quality.GOOD)],
    )
    publish_envelope(envelope)
    time.sleep(4.0)

    health = opcua_health()
    key = f"mdm-trusted/smartmeter/{DEVICE_ID}/power_kw"
    m = health.get("latest_measurements", {}).get(key)
    check("OPC UA connector consumed the trusted measurement at all", m is not None)
    if m:
        check("value propagated exactly", m["value"] == 17.25)
        check("quality propagation: GOOD -> status_code starts with 'Good'", str(m["status_code"]).startswith("Good"))
        check("quality propagation: marked valid", m["valid"] is True)
        check("timestamp propagation: source_timestamp matches envelope", m["source_timestamp"] == envelope.timestamp_utc)
        check("timestamp propagation: server_timestamp present (MDM's processed_at)", bool(m["server_timestamp"]))
        check("metadata propagation: tenant_id", m["metadata"] and m["metadata"].get("tenant_id") == "sit-tenant-b")
        check("metadata propagation: feeder_id (real grid_nodes topology)",
              m["metadata"] and m["metadata"].get("feeder_id") == "SIT-FDR-01")
        check("metadata propagation: transformer_id", m["metadata"] and m["metadata"].get("transformer_id") == "SIT-TX-01")
    else:
        for _ in range(8):
            check("(skipped -- no measurement found)", False)

    # --- Case 2: MDM-escalated OUT_OF_RANGE -- quality propagation for the bad case ---
    envelope2 = make_envelope(
        DEVICE_ID, tenant_id="sit-tenant-b", sequence_number=9301,
        measurements=[Measurement(measurement_type="frequency", unit="Hz", value=999.0, quality=Quality.GOOD)],
    )
    publish_envelope(envelope2)
    time.sleep(4.0)

    health2 = opcua_health()
    key2 = f"mdm-trusted/smartmeter/{DEVICE_ID}/frequency"
    m2 = health2.get("latest_measurements", {}).get(key2)
    check("OPC UA connector consumed the escalated trusted measurement", m2 is not None)
    if m2:
        check("quality propagation: MDM's OUT_OF_RANGE escalation reaches OPC UA as Bad_OUT_OF_RANGE",
              m2["status_code"] == "Bad_OUT_OF_RANGE")
        check("quality propagation: marked invalid", m2["valid"] is False)
    else:
        for _ in range(2):
            check("(skipped -- no measurement found)", False)

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
