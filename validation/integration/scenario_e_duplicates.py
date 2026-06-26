"""SIT Scenario E — duplicate packets. Publishes the identical envelope
twice over the LIVE broker (not direct invocation) deliberately, because
both the ingestor's and MDM's dedup caches are in-process state that
persists across messages within one running service — exactly what's
already live and subscribed. Verifies: (1) the DB ends up with exactly one
row, not two, (2) MDM's live `mdm_duplicates_total` metric increments, (3)
whether a human operator would actually SEE a log line recording the drop
(the "audit" deliverable) -- both services log the drop at DEBUG level,
which is below the INFO level both processes run at, so in practice there is
currently no operator-visible audit trail for a dropped duplicate.
"""
import json
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")
sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation/validation/scripts")
from contracts import Measurement, Quality  # noqa: E402
from harness import make_envelope, publish_envelope, query_db  # noqa: E402

DEVICE_ID = "SIT-METER-005"


def metric_value(text: str, name: str) -> float:
    m = re.search(rf'^{name}(\{{[^}}]*\}})? ([0-9.]+)$', text, re.MULTILINE)
    return float(m.group(2)) if m else 0.0


def fetch_metrics() -> str:
    return subprocess.run(["curl", "-s", "http://localhost:9201/metrics"], capture_output=True, text=True, check=True).stdout


def main():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'}: {name}")

    before_dup_total = metric_value(fetch_metrics(), "mdm_duplicates_total")

    envelope = make_envelope(
        DEVICE_ID, sequence_number=6001,
        measurements=[Measurement(measurement_type="voltage", unit="V", value=229.9, quality=Quality.GOOD)],
    )
    publish_envelope(envelope)
    time.sleep(1.5)
    publish_envelope(envelope)  # identical resend -- same dedup_key for ingestor AND MDM
    time.sleep(2.5)

    rows = query_db(
        f"SELECT count(*) AS n FROM telemetry WHERE device_id='{DEVICE_ID}' "
        f"AND time = '{envelope.timestamp_utc}'::timestamptz;"
    )
    check("ingestor dedup: exactly 1 DB row despite 2 identical publishes", rows and int(rows[0]["n"]) == 1)

    after_dup_total = metric_value(fetch_metrics(), "mdm_duplicates_total")
    check("MDM live dedup: mdm_duplicates_total incremented", after_dup_total > before_dup_total)
    print(f"  mdm_duplicates_total: {before_dup_total} -> {after_dup_total}")

    ingestor_logs = subprocess.run(["docker", "logs", "diep-ingestor", "--since", "30s"],
                                    capture_output=True, text=True).stdout + subprocess.run(
        ["docker", "logs", "diep-ingestor", "--since", "30s"], capture_output=True, text=True).stderr
    mdm_logs = subprocess.run(["docker", "logs", "diep-mdm", "--since", "30s"],
                               capture_output=True, text=True).stdout + subprocess.run(
        ["docker", "logs", "diep-mdm", "--since", "30s"], capture_output=True, text=True).stderr

    ingestor_audit_visible = "duplicate" in ingestor_logs.lower()
    mdm_audit_visible = "duplicate" in mdm_logs.lower()
    print(f"  ingestor log mentions 'duplicate' (INFO level and above): {ingestor_audit_visible}")
    print(f"  MDM log mentions 'duplicate' (INFO level and above): {mdm_audit_visible}")
    check("FINDING: ingestor's duplicate-drop is NOT operator-visible at default log level (logger.debug)",
          ingestor_audit_visible is False)
    check("FINDING: MDM's duplicate-drop is ALSO NOT operator-visible at default log level (logger.debug)",
          mdm_audit_visible is False)

    passed = sum(1 for _, ok in checks if ok)
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
