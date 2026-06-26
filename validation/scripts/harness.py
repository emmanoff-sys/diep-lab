"""DIEP System Integration Test (SIT) harness — shared helpers for every
validation scenario script in this directory.

Uses the real `contracts.TelemetryEnvelope` (pure stdlib, no third-party
deps) to construct envelopes, so every payload this harness publishes is
guaranteed to satisfy the actual frozen contract, not a hand-typed
approximation of it.

MQTT publish goes through a throwaway `eclipse-mosquitto` container on the
same docker network, authenticating with the already-provisioned METER001
device certificate (../../certs/devices/METER001.{crt,key}) — the broker is
mTLS-only (8883, client cert required); see INTEGRATION_VALIDATION_REPORT.md
for why a new identity was deliberately NOT provisioned for this harness.
Envelope payloads carry their own `device_id`, which is what the
ingestor/MDM actually key off of (not the MQTT topic) — so publishing
synthetic SIT-METER-NNN readings through METER001's authorized topic is
sufficient and requires no broker/ACL changes.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/emmanoff_lab/projects/diep-lab/.claude/worktrees/dlms-driver-validation")

from contracts import Measurement, Quality, TelemetryEnvelope  # noqa: E402

REPO_ROOT = "/home/emmanoff_lab/projects/diep-lab"
NETWORK = "diep-lab_diep-net"
CERTS_DIR = f"{REPO_ROOT}/certs/devices"
PUBLISH_TOPIC = "diep/smartmeter/METER001"  # METER001's own authorized topic; device_id inside the JSON is what matters


def now_utc_iso(offset_seconds: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.isoformat().replace("+00:00", "Z")


def make_envelope(device_id: str, *, tenant_id: str = "sit-tenant", site_id: str = "SIT Validation Site",
                   meter_id: str | None = None, measurements: list[Measurement] | None = None,
                   sequence_number: int = 0, timestamp_utc: str | None = None,
                   correlation_id: str | None = None, schema_version: str = "1.0",
                   timestamp_source: str = "GATEWAY") -> TelemetryEnvelope:
    return TelemetryEnvelope(
        tenant_id=tenant_id,
        site_id=site_id,
        device_id=device_id,
        meter_id=meter_id or device_id,
        timestamp_utc=timestamp_utc or now_utc_iso(),
        measurements=measurements or [Measurement(measurement_type="voltage", unit="V", value=230.0)],
        sequence_number=sequence_number,
        correlation_id=correlation_id or str(uuid.uuid4()),
        schema_version=schema_version,
        timestamp_source=timestamp_source,
    )


def publish_json(payload: str, topic: str = PUBLISH_TOPIC) -> None:
    subprocess.run(
        [
            "docker", "run", "--rm", "--network", NETWORK,
            "-v", f"{CERTS_DIR}:/certs:ro",
            "eclipse-mosquitto",
            "mosquitto_pub", "-h", "diep-mqtt", "-p", "8883",
            "--cafile", "/certs/ca.crt", "--cert", "/certs/METER001.crt", "--key", "/certs/METER001.key",
            "-t", topic, "-m", payload,
        ],
        check=True, capture_output=True, text=True,
    )


def publish_envelope(envelope: TelemetryEnvelope, topic: str = PUBLISH_TOPIC) -> None:
    publish_json(envelope.to_json(), topic=topic)


def publish_raw(payload: dict, topic: str = PUBLISH_TOPIC) -> None:
    publish_json(json.dumps(payload), topic=topic)


def query_db(sql: str) -> list[dict]:
    """Runs a read-only query against diep-timescaledb via psql --csv and
    returns rows as dicts. Quoting note: `sql` is interpolated into a shell
    command run by this harness script itself (not user input — every
    caller in this validation/ directory is a fixed literal string written
    by this sprint), so this does not introduce a SQL/shell injection
    surface beyond what already existed for the harness's own test code."""
    result = subprocess.run(
        ["docker", "exec", "-i", "diep-timescaledb", "psql", "-U", "diep", "-d", "diep", "--csv", "-c", sql],
        check=True, capture_output=True, text=True,
    )
    lines = result.stdout.strip().splitlines()
    if not lines:
        return []
    import csv
    reader = csv.DictReader(lines)
    return list(reader)


def exec_sql(sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", "diep-timescaledb", "psql", "-U", "diep", "-d", "diep", "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return result.stdout


def run_mdm_pipeline(raw_envelope_dict: dict, domain: str = "smartmeter") -> dict:
    """Direct in-process invocation of the REAL services.mdm.pipeline.MdmPipeline
    inside the running diep-mdm container (which has psycopg2/paho/
    prometheus_client installed) — used for deterministic per-scenario
    assertions on MDM's quality/dedup/timestamp/gap/enrichment logic, as a
    complement to (not a replacement for) the live broker connectivity
    check. See INTEGRATION_VALIDATION_REPORT.md methodology notes for why
    direct invocation is used instead of a live MQTT round-trip for MDM
    (the broker ACL does not currently grant MDM's identity write access to
    its own diep/+/+/trusted output topic — a finding in its own right)."""
    script = (
        "import json,sys; "
        "from services.mdm.pipeline import MdmPipeline; "
        f"raw = json.loads({json.dumps(json.dumps(raw_envelope_dict))}); "
        f"result = MdmPipeline().process(raw, domain={domain!r}); "
        "print(json.dumps({'accepted': result.accepted, 'reason': result.reason, "
        "'topic': result.topic, 'payload': result.payload}, default=str))"
    )
    result = subprocess.run(
        ["docker", "exec", "-i", "diep-mdm", "python3", "-c", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MDM pipeline invocation failed: {result.stderr}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_mdm_pipeline_batch(raw_envelope_dicts: list[dict], domain: str = "smartmeter") -> list[dict]:
    """Like run_mdm_pipeline, but processes every envelope through ONE
    MdmPipeline instance in a single docker exec call — needed for
    Scenario F's out-of-order detection, which is stateful per
    (tenant_id, device_id) across calls (services/mdm/timestamps.py's
    _last_sequence dict lives on the TimestampNormalizer instance, not
    anywhere global); a separate `docker exec` per envelope would get a
    fresh pipeline each time and could never see "out of order" at all."""
    script = (
        "import json,sys; "
        "from services.mdm.pipeline import MdmPipeline; "
        "pipeline = MdmPipeline(); "
        f"raws = json.loads({json.dumps(json.dumps(raw_envelope_dicts))}); "
        "results = []; "
        f"[results.append(pipeline.process(r, domain={domain!r})) for r in raws]; "
        "print(json.dumps([{'accepted': r.accepted, 'reason': r.reason, 'topic': r.topic, "
        "'payload': r.payload} for r in results], default=str))"
    )
    result = subprocess.run(
        ["docker", "exec", "-i", "diep-mdm", "python3", "-c", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MDM pipeline batch invocation failed: {result.stderr}")
    return json.loads(result.stdout.strip().splitlines()[-1])
