"""ADMS M7 test — DNP3 (mock) adapter selftest.

Runs the driver's own end-to-end selftest (connect -> read/normalize -> island /
grid_connect / set_setpoint against the bundled MockDnp3Outstation). Self-contained:
no API, no MQTT, no hardware — so it always runs.

Run:  python -m pytest tests/test_dnp3_adapter.py -q
"""
import subprocess
import sys
from pathlib import Path

DRIVERS = Path(__file__).resolve().parent.parent / "drivers"


def test_dnp3_driver_selftest():
    r = subprocess.run([sys.executable, "-m", "dnp3.selftest"],
                       cwd=str(DRIVERS), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DNP3 driver selftest PASSED" in r.stdout
