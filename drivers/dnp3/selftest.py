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
    print("bogus command rejected OK")

    # --- P3-3: pluggable transport selection ------------------------------
    from .transport import make_transport, RealDnp3Master
    from .sim import MockDnp3Outstation

    assert isinstance(make_transport("mock", 20000, {}), MockDnp3Outstation)
    assert isinstance(make_transport("", 20000, {"transport": "mock"}), MockDnp3Outstation)
    # A real outstation address (or explicit tcp) selects the real master.
    assert isinstance(make_transport("10.0.0.5", 20000, {}), RealDnp3Master)
    assert isinstance(make_transport("mock", 20000, {"transport": "tcp"}), RealDnp3Master)
    print("transport selection OK: mock default, tcp for real hosts")

    # Selecting the real master without pydnp3 must fail clearly, not silently.
    try:
        make_transport("10.0.0.5", 20000, {}).connect()
        real_ok = True  # pydnp3 present (field host); nothing to assert here
    except RuntimeError as exc:
        real_ok = False
        assert "pydnp3" in str(exc), exc
    print("real transport guard OK:",
          "pydnp3 present" if real_ok else "clear error when pydnp3 absent")

    print("DNP3 driver selftest PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
