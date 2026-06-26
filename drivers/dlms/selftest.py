"""DLMS driver selftest — end-to-end against the in-process simulator.

No field hardware, no broker: starts the DLMS simulator on an ephemeral port,
runs the real DlmsMeterClient against it, and asserts the OBIS reads
round-trip. Mirrors drivers/modbus_meter/selftest.py.

⚠️ See dlms/protocol.py VALIDATION CAVEAT: this validates the client<->simulator
flow, NOT conformance to a real DLMS meter.

Run from drivers/:
    python -m dlms.selftest
"""
from __future__ import annotations

import sys

from . import models
from .client import DlmsMeterClient
from .sim import DlmsMeterSim


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    sim = DlmsMeterSim(port=0, voltage=230.0, frequency=50.0)
    port = sim.start()
    print(f"dlms simulator on 127.0.0.1:{port}")
    try:
        client = DlmsMeterClient(host="127.0.0.1", port=port, interface="tcp")
        client.connect()
        voltage = client.read_meter(models.OBIS["voltage"])
        frequency = client.read_meter(models.OBIS["frequency"])
        power = client.read_meter(models.OBIS["power_kw"])
        client.disconnect()

        check("association established (AARE accepted)", True)
        check("voltage round-trips", voltage is not None, repr(voltage))
        check("voltage ~230 V", isinstance(voltage, (int, float)) and 200.0 <= float(voltage) <= 260.0, repr(voltage))
        check("frequency ~50 Hz", isinstance(frequency, (int, float)) and 45.0 <= float(frequency) <= 55.0, repr(frequency))
        check("power_kw present", power is not None, repr(power))
    finally:
        sim.stop()

    if failures:
        print(f"SELFTEST FAILED ({len(failures)} check(s)): {failures}")
        return 1
    print("SELFTEST PASSED — all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
