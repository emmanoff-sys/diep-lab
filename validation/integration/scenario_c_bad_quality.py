"""SIT Scenario C — bad quality data: INVALID, OUT_OF_RANGE,
COMMUNICATION_FAILURE. Two distinct cases, deliberately:

1. Driver-pre-flagged (the source already says INVALID/COMMUNICATION_FAILURE)
   -> must propagate UNCHANGED through both the ingestor and MDM (MDM's
   quality engine only ever escalates FROM GOOD, never overwrites).
2. GOOD-flagged but genuinely out of range / non-finite -> the ingestor
   passes it through as GOOD (it does not interpret quality at all), while
   MDM's own engine escalates it. This is the concrete illustration of the
   architecture gap from the sprint's central finding: the DB ends up
   showing GOOD forever for this reading; only MDM's (currently
   unreachable) trusted stream reflects OUT_OF_RANGE/INVALID.
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
        ("INVALID", Quality.INVALID, 9999.0, 4101),
        ("COMMUNICATION_FAILURE", Quality.COMMUNICATION_FAILURE, 0.0, 4102),
    ]
    for label, quality, value, seq in pre_flagged:
        envelope = make_envelope(
            DEVICE_ID, sequence_number=seq,
            measurements=[Measurement(measurement_type="current", unit="A", value=value, quality=quality)],
        )
        raw = envelope.to_dict()
        publish_envelope(envelope)
        time.sleep(1.5)

        rows = query_db(
            f"SELECT metadata FROM telemetry WHERE device_id='{DEVICE_ID}' "
            f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
        )
        db_quality = json.loads(rows[0]["metadata"])["quality"]["current"]["quality"] if rows else None
        check(f"[driver-flagged {label}] ingestor/DB preserves quality unchanged", db_quality == label)

        mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
        mdm_quality = mdm_result["payload"]["measurements"][0]["quality"]
        check(f"[driver-flagged {label}] MDM preserves quality unchanged (no transition)",
              mdm_quality == label and mdm_result["payload"]["mdm"]["quality_transitions"] == [])

    # --- Case 2: GOOD-flagged but actually bad -- MDM must escalate, ingestor must not ---
    cases_2 = [
        ("OUT_OF_RANGE (frequency=999Hz)", "frequency", "Hz", 999.0, 4103, "OUT_OF_RANGE", "out_of_range", True),
        # NOT "INVALID, propagates as GOOD" as originally hypothesized — see
        # the FAIL this surfaced below. A NaN value never reaches the DB at
        # all: `requests` (used by the ingestor's POST /telemetry call)
        # refuses to serialize NaN ("Out of range float values are not JSON
        # compliant: nan", raised as InvalidJSONError) and the ingestor's
        # except clause just logs and drops it — no retry, no dead-letter,
        # no alert. This is silent data loss, not a quality-flag gap, and a
        # materially worse finding than what this case was written to show.
        ("INVALID (non-finite value)", "voltage", "V", float("nan"), 4104, "INVALID", "non_finite_value", False),
    ]
    for label, mtype, unit, value, seq, expected_quality, expected_reason, expect_db_row in cases_2:
        envelope = make_envelope(
            DEVICE_ID, sequence_number=seq,
            measurements=[Measurement(measurement_type=mtype, unit=unit, value=value, quality=Quality.GOOD)],
        )
        raw = envelope.to_dict()
        publish_envelope(envelope)
        time.sleep(1.5)

        rows = query_db(
            f"SELECT metadata FROM telemetry WHERE device_id='{DEVICE_ID}' "
            f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
        )
        if expect_db_row:
            db_quality = json.loads(rows[0]["metadata"])["quality"][mtype]["quality"] if rows else None
            check(f"[{label}] ingestor/DB still shows GOOD (does not interpret quality) -- THE GAP",
                  db_quality == "GOOD")
            print(f"  -> DB shows quality={db_quality!r}")
        else:
            check(f"[{label}] SILENT DATA LOSS: no DB row at all (ingestor's POST failed and was dropped)",
                  len(rows) == 0)
            print("  -> DB has NO row for this reading at all (see ingestor log: InvalidJSONError on NaN)")

        mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
        mdm_meas = mdm_result["payload"]["measurements"][0]
        transitions = mdm_result["payload"]["mdm"]["quality_transitions"]
        check(f"[{label}] MDM escalates to {expected_quality}", mdm_meas["quality"] == expected_quality)
        check(f"[{label}] MDM records an explicit, attributable transition (reason={expected_reason})",
              len(transitions) == 1 and transitions[0]["reason"] == expected_reason
              and transitions[0]["original_quality"] == "GOOD")
        print(f"  -> MDM trusted stream would show quality={mdm_meas['quality']!r} (but nothing consumes that stream today)")

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
