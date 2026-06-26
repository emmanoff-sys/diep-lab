"""SIT Scenario C — bad quality data: INVALID, OUT_OF_RANGE,
COMMUNICATION_FAILURE. Two distinct cases, deliberately:

1. Driver-pre-flagged (the source already says INVALID/COMMUNICATION_FAILURE)
   -> must propagate UNCHANGED through both the ingestor and MDM (MDM's
   quality engine only ever escalates FROM GOOD, never overwrites).
2. GOOD-flagged but genuinely out of range / non-finite -> MDM's engine
   escalates it, and (post-stabilization-sprint Work Item 4) the DB now
   reflects that escalation too, because the ingestor reads MDM's "trusted"
   stream rather than the raw one.

Round 2 (post-stabilization sprint): this scenario originally asserted the
*bug* here -- the DB showing GOOD forever for an out-of-range reading, and
NaN causing silent data loss with no DB row at all (see git history for the
original version, and SYSTEM_ACCEPTANCE_REPORT.md / PIPELINE_VALIDATION_REPORT.md
for the before/after). Both are fixed now (Work Items 1 and 4): every case
gets a DB row, and that row shows the *escalated* quality, not the raw one.
"""
import json
import sys
import time

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, publish_envelope, query_db, run_mdm_pipeline  # noqa: E402

DEVICE_ID = "SIT-METER-003"


def main():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    # --- Case 1: driver-pre-flagged, must never be overwritten ---
    pre_flagged = [
        ("INVALID", Quality.INVALID, 9999.0, 4201),
        ("COMMUNICATION_FAILURE", Quality.COMMUNICATION_FAILURE, 0.0, 4202),
    ]
    for label, quality, value, seq in pre_flagged:
        envelope = make_envelope(
            DEVICE_ID, sequence_number=seq,
            measurements=[Measurement(measurement_type="current", unit="A", value=value, quality=quality)],
        )
        raw = envelope.to_dict()
        publish_envelope(envelope)
        time.sleep(4.0)  # raw -> MDM -> trusted -> ingestor -> FastAPI -> DB, one more hop than Round 1

        rows = query_db(
            f"SELECT metadata FROM telemetry WHERE device_id='{DEVICE_ID}' "
            f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
        )
        db_quality = json.loads(rows[0]["metadata"])["quality"]["current"]["quality"] if rows else None
        check(f"[driver-flagged {label}] DB preserves quality unchanged through MDM + ingestor", db_quality == label)

        mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
        mdm_quality = mdm_result["payload"]["measurements"][0]["quality"]
        check(f"[driver-flagged {label}] MDM preserves quality unchanged (no transition)",
              mdm_quality == label and mdm_result["payload"]["mdm"]["quality_transitions"] == [])

    # --- Case 2: GOOD-flagged but actually bad -- MDM escalates, and (since
    # Work Item 4) the DB now shows that escalation, not the raw GOOD value ---
    cases_2 = [
        ("OUT_OF_RANGE (frequency=999Hz)", "frequency", "Hz", 999.0, 4203,
         "OUT_OF_RANGE", "out_of_range", "OUT_OF_RANGE"),
        # The ingestor's OWN non-finite guard (Work Item 1) also independently
        # catches this -- it doesn't rely on MDM having already escalated it
        # to do so -- so the DB's `rejected_reason` is the ingestor's own,
        # while `original_quality` reflects whatever quality the message
        # already carried by the time the ingestor saw it (MDM's escalated
        # INVALID, since this travels via the trusted topic).
        ("INVALID (non-finite value)", "voltage", "V", float("nan"), 4204,
         "INVALID", "non_finite_value", "INVALID"),
    ]
    for label, mtype, unit, value, seq, expected_mdm_quality, expected_mdm_reason, expected_db_quality in cases_2:
        envelope = make_envelope(
            DEVICE_ID, sequence_number=seq,
            measurements=[Measurement(measurement_type=mtype, unit=unit, value=value, quality=Quality.GOOD)],
        )
        raw = envelope.to_dict()
        publish_envelope(envelope)
        time.sleep(4.0)

        rows = query_db(
            f"SELECT metadata FROM telemetry WHERE device_id='{DEVICE_ID}' "
            f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
        )
        check(f"[{label}] a DB row exists (no silent loss)", len(rows) == 1)
        db_field_quality = json.loads(rows[0]["metadata"])["quality"].get(mtype) if rows else None
        db_quality = db_field_quality.get("quality") if db_field_quality else None
        check(f"[{label}] DB reflects the escalated quality ({expected_db_quality}), not raw GOOD",
              db_quality == expected_db_quality)
        print(f"  -> DB shows quality={db_quality!r} (metadata: {db_field_quality})")

        mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
        mdm_meas = mdm_result["payload"]["measurements"][0]
        transitions = mdm_result["payload"]["mdm"]["quality_transitions"]
        check(f"[{label}] MDM escalates to {expected_mdm_quality}", mdm_meas["quality"] == expected_mdm_quality)
        check(f"[{label}] MDM records an explicit, attributable transition (reason={expected_mdm_reason})",
              len(transitions) == 1 and transitions[0]["reason"] == expected_mdm_reason
              and transitions[0]["original_quality"] == "GOOD")

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
