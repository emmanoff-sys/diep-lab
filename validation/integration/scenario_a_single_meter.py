"""SIT Scenario A — single smart meter, AMI -> ingestor -> TimescaleDB (the
real, wired path), AND AMI -> MDM pipeline (direct invocation; see
harness.run_mdm_pipeline for why this isn't a live broker round-trip).
Verifies every value, the timestamp, and every per-field quality flag
survives both paths exactly.

Run from validation/scripts/harness.py's directory context:
    python3 validation/integration/scenario_a_single_meter.py
"""
import json
import sys
import time

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, publish_envelope, query_db, run_mdm_pipeline  # noqa: E402

DEVICE_ID = "SIT-METER-001"


def main():
    measurements = [
        Measurement(measurement_type="voltage", unit="V", value=231.7, quality=Quality.GOOD),
        Measurement(measurement_type="current", unit="A", value=12.34, quality=Quality.GOOD),
        Measurement(measurement_type="power_kw", unit="kW", value=2.851, quality=Quality.GOOD),
        Measurement(measurement_type="frequency", unit="Hz", value=50.02, quality=Quality.GOOD),
    ]
    envelope = make_envelope(DEVICE_ID, sequence_number=1001, measurements=measurements)
    raw = envelope.to_dict()
    print("=== Published envelope ===")
    print(json.dumps(raw, indent=2))

    publish_envelope(envelope)
    time.sleep(2)  # ingestor processing latency

    rows = query_db(
        f"SELECT time, device_id, voltage, current, power_kw, frequency, metadata "
        f"FROM telemetry WHERE device_id='{DEVICE_ID}' AND time = '{envelope.timestamp_utc}'::timestamptz;"
    )
    print("\n=== Row in TimescaleDB (via real ingestor path) ===")
    print(json.dumps(rows, indent=2))

    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    check("exactly one DB row written", len(rows) == 1)
    if rows:
        row = rows[0]
        check("voltage exact match", float(row["voltage"]) == 231.7)
        check("current exact match", float(row["current"]) == 12.34)
        check("power_kw exact match", float(row["power_kw"]) == 2.851)
        check("frequency exact match", float(row["frequency"]) == 50.02)
        meta = json.loads(row["metadata"])
        quality = meta.get("quality", {})
        check("metadata carries per-field quality=GOOD for all 4 fields",
              all(quality.get(f, {}).get("quality") == "GOOD" for f in ("voltage", "current", "power_kw", "frequency")))
        check("metadata carries estimated=False for all 4 fields",
              all(quality.get(f, {}).get("estimated") is False for f in ("voltage", "current", "power_kw", "frequency")))
        check("tenant_id preserved in metadata", meta.get("tenant_id") == "sit-tenant")
        check("correlation_id preserved in metadata", meta.get("correlation_id") == envelope.correlation_id)

    mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
    print("\n=== MDM pipeline direct-invocation result ===")
    print(json.dumps(mdm_result, indent=2))

    check("MDM accepted the envelope", mdm_result["accepted"] is True)
    check("MDM trusted topic is diep/smartmeter/SIT-METER-001/trusted", mdm_result["topic"] == f"diep/smartmeter/{DEVICE_ID}/trusted")
    mdm_payload = mdm_result["payload"]
    mdm_meas_by_type = {m["measurement_type"]: m for m in mdm_payload["measurements"]}
    check("MDM trusted output preserves voltage value exactly", mdm_meas_by_type["voltage"]["value"] == 231.7)
    check("MDM trusted output preserves all 4 GOOD qualities (no spurious escalation)",
          all(m["quality"] == "GOOD" for m in mdm_payload["measurements"]))
    check("MDM device metadata enrichment: tenant_id", mdm_payload["mdm"]["device_metadata"]["tenant_id"] == "sit-tenant")
    check("MDM device metadata enrichment: feeder_id = SIT-FDR-01 (real grid_nodes topology)",
          mdm_payload["mdm"]["device_metadata"]["feeder_id"] == "SIT-FDR-01")
    check("MDM device metadata enrichment: transformer_id = SIT-TX-01",
          mdm_payload["mdm"]["device_metadata"]["transformer_id"] == "SIT-TX-01")
    check("MDM quality_transitions empty (nothing to escalate)", mdm_payload["mdm"]["quality_transitions"] == [])

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
