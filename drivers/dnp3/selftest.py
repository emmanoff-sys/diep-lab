"""End-to-end selftest for the DNP3 (mock) driver — no MQTT, no hardware.

Exercises connect -> read_telemetry -> normalize and the island / grid_connect /
set_setpoint controls against the bundled MockDnp3Outstation, asserting the
canonical mapping and control effects.

Run from drivers/:  python -m dnp3.selftest
"""
from __future__ import annotations

import sys

from .driver import Dnp3Driver


def main() -> int:
    d = Dnp3Driver("MGD900", {"host": "mock"})
    d.connect()

    canon = d.normalize(d.read_telemetry())
    assert {"voltage", "frequency", "power_kw", "grid_import_kw", "grid_export_kw"} <= set(canon), canon
    assert canon["mode"] == "grid_connected", canon
    print("read/normalize OK:", {k: canon[k] for k in ("voltage", "frequency", "power_kw", "mode")})

    assert d.execute_command("island", {}).status == "ACKED"
    islanded = d.normalize(d.read_telemetry())
    assert islanded["mode"] == "islanded" and islanded["power_kw"] == 0.0, islanded
    print("island OK: PCC=0, mode=islanded")

    assert d.execute_command("grid_connect", {}).status == "ACKED"
    assert d.execute_command("set_setpoint", {"setpoint_kw": 100}).status == "ACKED"
    reconnected = d.normalize(d.read_telemetry())
    assert reconnected["mode"] == "grid_connected", reconnected
    assert reconnected["power_kw"] == 100.0, reconnected
    print("grid_connect + set_setpoint OK: PCC=100, mode=grid_connected")

    assert d.execute_command("bogus", {}).status == "FAILED"
    print("DNP3 driver selftest PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
