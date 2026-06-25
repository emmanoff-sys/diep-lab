"""SIT Scenario D — estimated values survive the entire pipeline: DB
metadata and MDM's trusted output must both preserve quality=ESTIMATED /
estimated=True unchanged (MDM never overwrites a non-GOOD flag). Also
exercises the contract's own auto-correction rule (ESTIMATED quality implies
estimated=True even if the driver sent estimated=False)."""
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

    # estimated=False sent alongside ESTIMATED quality -- contract's
    # __post_init__ must auto-correct this to estimated=True.
    envelope = make_envelope(
        DEVICE_ID, sequence_number=5001,
        measurements=[Measurement(measurement_type="power_kw", unit="kW", value=3.2, quality=Quality.ESTIMATED, estimated=False)],
    )
    raw = envelope.to_dict()
    check("contract auto-corrects estimated=True when quality=ESTIMATED",
          raw["measurements"][0]["estimated"] is True)

    publish_envelope(envelope)
    time.sleep(1.5)

    rows = query_db(
        f"SELECT power_kw, metadata FROM telemetry WHERE device_id='{DEVICE_ID}' "
        f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
    )
    check("DB row written", len(rows) == 1)
    if rows:
        meta = json.loads(rows[0]["metadata"])
        pf = meta["quality"]["power_kw"]
        check("DB metadata: quality=ESTIMATED preserved", pf["quality"] == "ESTIMATED")
        check("DB metadata: estimated=True preserved", pf["estimated"] is True)
        check("DB value itself unchanged (3.2)", float(rows[0]["power_kw"]) == 3.2)

    mdm_result = run_mdm_pipeline(raw, domain="smartmeter")
    mdm_meas = mdm_result["payload"]["measurements"][0]
    check("MDM trusted output: quality=ESTIMATED preserved", mdm_meas["quality"] == "ESTIMATED")
    check("MDM trusted output: estimated=True preserved", mdm_meas["estimated"] is True)
    check("MDM recorded no quality transition (never overwrites non-GOOD)",
          mdm_result["payload"]["mdm"]["quality_transitions"] == [])
    check("MDM trusted output value unchanged (3.2)", mdm_meas["value"] == 3.2)

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
