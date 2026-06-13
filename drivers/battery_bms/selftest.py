"""End-to-end selftest for the battery / BMS driver against its simulator.

No field hardware, no broker, no extra deps: starts the Modbus-TCP battery
simulator on an ephemeral port, runs the real BatteryBmsDriver against it, and
asserts canonical + extra telemetry and the charge/discharge/standby lifecycle
(including the DERMS-style target_soc / max_power_kw command shape).

A small capacity is used so SoC moves observably within the test window.

Run from drivers/:
    python -m battery_bms.selftest
"""
from __future__ import annotations

import sys
import time

from battery_bms.sim import BatteryBmsSim
from battery_bms.driver import BatteryBmsDriver


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    sim = BatteryBmsSim(capacity_kwh=10.0, soc=50.0, port=0)
    port = sim.start()
    print(f"battery simulator on 127.0.0.1:{port}")

    driver = BatteryBmsDriver("BAT900", {"host": "127.0.0.1", "port": port, "default_power_kw": 50})
    try:
        # 1. connect + telemetry decode (standby at rest)
        driver.connect()
        t = driver.normalize(driver.read_telemetry())
        print(f"  telemetry: {t}")
        check("canonical fields present",
              all(k in t for k in ("battery_soc", "power_kw", "voltage", "current")))
        check("extras present", all(k in t for k in ("temperature", "soh", "state")))
        check("voltage ~ 700 V", 680 <= t["voltage"] <= 720, f"{t['voltage']}")
        check("starts in STANDBY", t["state"] == "STANDBY", t["state"])
        check("standby power is 0", t["power_kw"] == 0, f"{t['power_kw']}")

        # 2. charge -> negative power, CHARGING, SoC rises
        soc0 = driver.read_telemetry()["battery_soc"]
        check("charge ACKED", driver.execute_command("charge", {"power_kw": 50}).status == "ACKED")
        time.sleep(1.5)
        tc = driver.normalize(driver.read_telemetry())
        print(f"  charging: power={tc['power_kw']} state={tc['state']} soc={tc['battery_soc']}")
        check("charge -> negative power", tc["power_kw"] < 0, f"{tc['power_kw']}")
        check("charge -> CHARGING state", tc["state"] == "CHARGING", tc["state"])
        check("charge raises SoC", tc["battery_soc"] > soc0, f"{soc0} -> {tc['battery_soc']}")

        # 3. discharge -> positive power, DISCHARGING, SoC falls
        soc1 = driver.read_telemetry()["battery_soc"]
        check("discharge ACKED", driver.execute_command("discharge", {"power_kw": 50}).status == "ACKED")
        time.sleep(1.5)
        td = driver.normalize(driver.read_telemetry())
        print(f"  discharging: power={td['power_kw']} state={td['state']} soc={td['battery_soc']}")
        check("discharge -> positive power", td["power_kw"] > 0, f"{td['power_kw']}")
        check("discharge -> DISCHARGING state", td["state"] == "DISCHARGING", td["state"])
        check("discharge lowers SoC", td["battery_soc"] < soc1, f"{soc1} -> {td['battery_soc']}")

        # 4. set_power_limit caps effective power (limit below setpoint)
        check("set_power_limit ACKED",
              driver.execute_command("set_power_limit", {"power_kw": 10}).status == "ACKED")
        driver.execute_command("discharge", {"power_kw": 50})  # ask 50, limited to 10
        time.sleep(0.4)
        tl = driver.normalize(driver.read_telemetry())
        print(f"  limited discharge: power={tl['power_kw']}")
        check("power limit enforced (<=10kW)", abs(tl["power_kw"]) <= 10.05, f"{tl['power_kw']}")

        # 5. standby -> 0 kW, STANDBY
        check("standby ACKED", driver.execute_command("standby", {}).status == "ACKED")
        time.sleep(0.4)
        ts = driver.normalize(driver.read_telemetry())
        check("standby zeroes power", ts["power_kw"] == 0, f"{ts['power_kw']}")
        check("standby -> STANDBY state", ts["state"] == "STANDBY", ts["state"])

        # 6. DERMS-shaped charge (target_soc + max_power_kw) is accepted
        check("DERMS-style charge ACKED",
              driver.execute_command("charge", {"target_soc": 90, "max_power_kw": 25}).status == "ACKED")

        # 7. validation
        check("set_power_limit w/o param FAILED",
              driver.execute_command("set_power_limit", {}).status == "FAILED")
        check("unknown command FAILED",
              driver.execute_command("explode", {}).status == "FAILED")
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
