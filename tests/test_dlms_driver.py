"""Integration test: DlmsMeterClient round-trips OBIS reads against the
in-process DLMS simulator (no hardware, no broker).

⚠️ The DLMS wire encoding under test is a minimal, not-yet-meter-validated
subset — see drivers/dlms/protocol.py. This test proves the client<->simulator
flow, NOT conformance to a real DLMS meter.
"""
import os
import sys

import pytest

# Make the drivers/ package importable (dlms + diep_driver) without a global
# pytest/conftest change — minimal, additive test infra.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "drivers"))

from dlms import models  # noqa: E402
from dlms.client import DlmsMeterClient  # noqa: E402
from dlms.sim import DlmsMeterSim  # noqa: E402


def test_obis_round_trip():
    sim = DlmsMeterSim(host="127.0.0.1", port=0, voltage=231.5, frequency=49.9)
    port = sim.start()
    try:
        with DlmsMeterClient(host="127.0.0.1", port=port, interface="tcp") as client:
            voltage = client.read_meter(models.OBIS["voltage"])
            frequency = client.read_meter(models.OBIS["frequency"])
        assert voltage is not None
        assert 230.0 <= float(voltage) <= 232.0
        assert 45.0 <= float(frequency) <= 55.0
    finally:
        sim.stop()


def test_adapter_exposes_telemetry():
    """The BaseDriver adapter returns the canonical OBIS fields."""
    from dlms.driver import DlmsMeterDriver

    sim = DlmsMeterSim(host="127.0.0.1", port=0, voltage=228.0, frequency=50.0)
    port = sim.start()
    try:
        driver = DlmsMeterDriver("METER-DLMS-TEST", {"host": "127.0.0.1", "port": port})
        driver.connect()
        try:
            telemetry = driver.read_telemetry()
        finally:
            driver.disconnect()
        assert set(models.OBIS) <= set(telemetry)
        assert 220.0 <= float(telemetry["voltage"]) <= 240.0
    finally:
        sim.stop()


def test_rejected_association_raises():
    """A rejected AARE surfaces as a ConnectionError from connect()."""
    sim = DlmsMeterSim(host="127.0.0.1", port=0, reject=True)
    port = sim.start()
    try:
        client = DlmsMeterClient(host="127.0.0.1", port=port, interface="tcp")
        with pytest.raises(ConnectionError):
            client.connect()
    finally:
        sim.stop()


def test_unknown_obis_raises():
    """Reading an OBIS the meter does not serve surfaces as an IOError."""
    sim = DlmsMeterSim(host="127.0.0.1", port=0)
    port = sim.start()
    try:
        with DlmsMeterClient(host="127.0.0.1", port=port, interface="tcp") as client:
            with pytest.raises(IOError):
                client.read_meter("99.99.99.99.99.255")  # not in the sim's OBIS map
    finally:
        sim.stop()
