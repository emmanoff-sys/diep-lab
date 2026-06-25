"""Deliverable 5 supplement — the 3 quality flags not yet exercised by
Scenarios A-F (SUBSTITUTED, MISSING, DUPLICATE): driver-pre-flagged, must
survive unchanged through both the DB metadata and MDM's trusted output.
Combined with Scenario A (GOOD), C (INVALID/OUT_OF_RANGE/COMMUNICATION_FAILURE)
and D (ESTIMATED), this completes coverage of all 8 contracts.Quality flags.
"""
import json
import sys
import time

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, publish_envelope, query_db, run_mdm_pipeline  # noqa: E402

DEVICE_ID = "SIT-METER-004"


def main():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    cases = [
        ("SUBSTITUTED", Quality.SUBSTITUTED, 225.0, 7001),
        ("MISSING", Quality.MISSING, 0.0, 7002),
        ("DUPLICATE", Quality.DUPLICATE, 225.5, 7003),
    ]
    for label, quality, value, seq in cases:
        envelope = make_envelope(
            DEVICE_ID, sequence_number=seq,
            measurements=[Measurement(measurement_type="voltage", unit="V", value=value, quality=quality)],
        )
        raw = envelope.to_dict()
        publish_envelope(envelope)
        time.sleep(1.5)

        rows = query_db(
            f"SELECT metadata FROM telemetry WHERE device_id='{DEVICE_ID}' "
            f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
        )
        db_quality = json.loads(rows[0]["metadata"])["quality"]["voltage"]["quality"] if rows else None
        check(f"[{label}] DB metadata preserves quality unchanged", db_quality == label)

        mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
        mdm_quality = mdm_result["payload"]["measurements"][0]["quality"]
        check(f"[{label}] MDM preserves quality unchanged (no transition)",
              mdm_quality == label and mdm_result["payload"]["mdm"]["quality_transitions"] == [])

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
