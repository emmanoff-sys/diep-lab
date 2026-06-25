"""AMI Ingest Phase 4 — proves drivers/dlms actually publishes the contract
(the "AMI Ingest publishes it" success criterion), not just that the contract
module validates in isolation. Companion to test_contracts_telemetry.py and
test_dlms_driver.py.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "drivers"))

from dlms.driver import DlmsMeterDriver  # noqa: E402
from dlms.sim import DlmsMeterSim  # noqa: E402
from diep_driver.runner import Runner  # noqa: E402
from contracts import TelemetryEnvelope  # noqa: E402


@pytest.fixture
def dlms_driver():
    sim = DlmsMeterSim(host="127.0.0.1", port=0)
    port = sim.start()
    driver = DlmsMeterDriver(
        "METER001",
        config={"host": "127.0.0.1", "port": port, "tenant_id": "tenantA", "site_id": "Abuja Site A"},
    )
    driver.connect()
    try:
        yield driver
    finally:
        driver.disconnect()
        sim.stop()


def test_dlms_driver_opts_into_contract_envelope(dlms_driver):
    assert dlms_driver.use_contract_envelope is True
    assert dlms_driver.protocol == "dlms"


def test_dlms_runner_emits_valid_envelope(dlms_driver):
    runner = Runner(dlms_driver, transport=object())  # transport unused by _build_envelope
    native = dlms_driver.read_telemetry()
    normalized = dlms_driver.normalize(native)
    message = runner._build_envelope(normalized)

    envelope = TelemetryEnvelope.from_json(message)  # raises ContractValidationError if malformed
    assert envelope.device_id == "METER001"
    assert envelope.tenant_id == "tenantA"
    assert envelope.site_id == "Abuja Site A"
    assert envelope.source_protocol == "dlms"

    by_type = {m.measurement_type: m for m in envelope.measurements}
    assert set(by_type) == {"voltage", "current", "power_kw", "frequency"}, (
        "only the 4 fields DLMS actually measures should be present — no "
        "phantom 0.0 readings for solar_kw/battery_soc/grid_import_kw/grid_export_kw"
    )
    assert by_type["voltage"].unit == "V"
    assert all(m.quality.value == "GOOD" for m in envelope.measurements)


def test_dlms_runner_increments_sequence_number_per_cycle(dlms_driver):
    runner = Runner(dlms_driver, transport=object())
    native = dlms_driver.read_telemetry()
    normalized = dlms_driver.normalize(native)
    seq_a = TelemetryEnvelope.from_json(runner._build_envelope(normalized)).sequence_number
    seq_b = TelemetryEnvelope.from_json(runner._build_envelope(normalized)).sequence_number
    assert seq_b == seq_a + 1


def test_dlms_envelope_matches_json_schema(dlms_driver):
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = os.path.join(os.path.dirname(__file__), "..", "contracts", "schema", "telemetry.schema.json")
    with open(schema_path) as f:
        schema = json.load(f)

    runner = Runner(dlms_driver, transport=object())
    native = dlms_driver.read_telemetry()
    normalized = dlms_driver.normalize(native)
    message = runner._build_envelope(normalized)

    jsonschema.validate(json.loads(message), schema)
