"""End-to-end selftest for the Modbus smart-meter driver against its simulator.

No field hardware, no broker, no extra deps: starts the Modbus-TCP meter simulator
on an ephemeral port, runs the real ModbusMeterDriver against it, and asserts
canonical + meter telemetry and the disconnect/reconnect relay lifecycle.

Run from drivers/:
    python -m modbus_meter.selftest
"""
from __future__ import annotations

import sys
import time

from modbus_meter.sim import ModbusMeterSim
from modbus_meter.driver import ModbusMeterDriver


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    sim = ModbusMeterSim(base_load_kw=3.5, swing_kw=1.0, period_s=60.0, port=0)
    port = sim.start()
    print(f"meter simulator on 127.0.0.1:{port}")

    driver = ModbusMeterDriver("MTR900", {"host": "127.0.0.1", "port": port})
    try:
        # 1. connect + telemetry decode
        driver.connect()
        t = driver.normalize(driver.read_telemetry())
        print(f"  telemetry: {t}")
        check("canonical fields present",
              all(k in t for k in ("voltage", "current", "power_kw", "frequency",
                                   "grid_import_kw", "grid_export_kw")))
        check("meter extras present",
              all(k in t for k in ("power_factor", "energy_import_kwh", "energy_export_kwh")))
        check("voltage ~ 230 V", 220.0 <= t["voltage"] <= 240.0, f"{t['voltage']}")
        check("frequency ~ 50 Hz", 49.0 <= t["frequency"] <= 51.0, f"{t['frequency']}")
        check("power > 0 while connected", t["power_kw"] > 0, f"{t['power_kw']} kW")
        check("import mirrors active power",
              abs(t["grid_import_kw"] - t["power_kw"]) < 1e-6)
        check("power factor ~ 0.98", 0.9 <= t["power_factor"] <= 1.0, f"{t['power_factor']}")

        # 2. energy counter accumulates
        e1 = driver.read_telemetry()["energy_import_kwh"]
        time.sleep(1.2)
        e2 = driver.read_telemetry()["energy_import_kwh"]
        check("energy_import accumulates", e2 >= e1, f"{e1} -> {e2}")

        # 3. remote_disconnect -> power collapses, relay open
        res = driver.execute_command("remote_disconnect", {})
        check("remote_disconnect ACKED", res.status == "ACKED", res.error or "")
        time.sleep(0.2)
        td = driver.normalize(driver.read_telemetry())
        print(f"  after disconnect: power={td['power_kw']} relay={td.get('relay_state')}")
        check("disconnect zeroes power", td["power_kw"] == 0, f"{td['power_kw']}")
        check("relay shows disconnected", td.get("relay_state") == 0, f"{td.get('relay_state')}")

        # 4. remote_connect -> power restored
        res = driver.execute_command("remote_connect", {})
        check("remote_connect ACKED", res.status == "ACKED", res.error or "")
        time.sleep(0.2)
        tc = driver.normalize(driver.read_telemetry())
        print(f"  after reconnect: power={tc['power_kw']} relay={tc.get('relay_state')}")
        check("reconnect restores power", tc["power_kw"] > 0, f"{tc['power_kw']}")
        check("relay shows connected", tc.get("relay_state") == 1, f"{tc.get('relay_state')}")

        # 5. read_only latch then actuation refused
        check("read_only ACKED", driver.execute_command("read_only", {}).status == "ACKED")
        ro = driver.execute_command("remote_disconnect", {})
        check("actuation refused in read_only", ro.status == "FAILED", ro.error or "")
        driver._read_only = False  # reset for cleanliness

        # 6. unknown command rejected
        unknown = driver.execute_command("explode", {})
        check("unknown command FAILED", unknown.status == "FAILED", unknown.error or "")
    finally:
        driver.disconnect()
        sim.stop()

    print()
    if failures:
        print(f"SELFTEST FAILED ({len(failures)} check(s)): {failures}")
        return 1
    print("SELFTEST PASSED — all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
