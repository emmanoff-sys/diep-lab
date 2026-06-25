"""SIT Scenario F — out-of-order timestamps: late arrivals, clock drift,
future timestamps. Uses run_mdm_pipeline_batch (one MdmPipeline instance,
several envelopes) because out-of-order detection is sequence-number state
held on the TimestampNormalizer instance across calls — a fresh pipeline per
call could never observe it. The raw/ingestor path does not normalize
timestamps at all (passes timestamp_utc straight through as `time`) — that
asymmetry is itself part of what this scenario documents.
"""
import sys

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, now_utc_iso, run_mdm_pipeline_batch  # noqa: E402

DEVICE_ID = "SIT-METER-006"


def main():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    def env(seq, ts_offset_s=0.0):
        return make_envelope(
            DEVICE_ID, tenant_id="sit-tenant-b", sequence_number=seq,
            timestamp_utc=now_utc_iso(ts_offset_s),
            measurements=[Measurement(measurement_type="voltage", unit="V", value=230.0, quality=Quality.GOOD)],
        ).to_dict()

    # Sequence: normal(seq=10) -> normal(seq=11) -> LATE ARRIVAL (seq=9, a
    # straggler from before seq=10) -> normal(seq=12, must NOT be permanently
    # desynced by the straggler) -> clock-drifted(seq=13, captured 5 min ago)
    # -> future timestamp(seq=14, captured 5 min from now).
    envelopes = [
        env(10),
        env(11),
        env(9),                 # late arrival / out of order
        env(12),                # must recover from the straggler
        env(13, -300.0),        # clock drift: 5 minutes in the past
        env(14, 300.0),         # "future timestamp": 5 minutes ahead
    ]
    results = run_mdm_pipeline_batch(envelopes, domain="smartmeter")

    def ts(idx):
        return results[idx]["payload"]["mdm"]["timestamp_assessment"]

    check("seq=10 (first seen): not out of order", ts(0)["is_out_of_order"] is False)
    check("seq=11 (in order): not out of order", ts(1)["is_out_of_order"] is False)
    check("seq=9 (late arrival, < last seen 11): flagged out of order", ts(2)["is_out_of_order"] is True)
    check("seq=12 (after straggler): NOT permanently desynced, correctly not out of order",
          ts(3)["is_out_of_order"] is False)
    check("clock drift (captured 5 min ago): drift_seconds ~ +300s", 295 <= ts(4)["drift_seconds"] <= 305)
    check("clock drift (5 min past threshold of 30s): is_drifted=True", ts(4)["is_drifted"] is True)
    check("future timestamp (captured 5 min ahead): drift_seconds ~ -300s", -305 <= ts(5)["drift_seconds"] <= -295)
    check("future timestamp: is_drifted=True (drift is checked by magnitude, not just lag)", ts(5)["is_drifted"] is True)
    check("every envelope still gets an ingestion_timestamp stamped",
          all(r["payload"]["ingestion_timestamp"] for r in results))
    check("late/drifted/future timestamps do not affect quality (still GOOD; orthogonal concerns)",
          all(r["payload"]["measurements"][0]["quality"] == "GOOD" for r in results))

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
