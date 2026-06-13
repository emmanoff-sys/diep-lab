"""End-to-end selftest for the microgrid IEC-104 driver against its RTU simulator.

No field hardware, no broker, no deps: starts the IEC-104 RTU on an ephemeral port,
runs the real MicrogridIec104Driver against it, and asserts canonical telemetry plus
the island / grid_connect / set_setpoint command lifecycle (incl. islanding droop).

Run from drivers/:
    python -m microgrid_iec104.selftest
"""
from __future__ import annotations

import sys
import time

from microgrid_iec104.sim import MicrogridRtuSim
from microgrid_iec104.driver import MicrogridIec104Driver


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    sim = MicrogridRtuSim(common_address=1, port=0)
    port = sim.start()
    print(f"microgrid RTU on 127.0.0.1:{port}")

    driver = MicrogridIec104Driver("MGC900", {"host": "127.0.0.1", "port": port, "common_address": 1})
    try:
        # 1. connect (STARTDT) + interrogation telemetry
        driver.connect()
        t = driver.normalize(driver.read_telemetry())
        print(f"  telemetry: {t}")
        check("canonical fields present",
              all(k in t for k in ("voltage", "frequency", "solar_kw", "power_kw",
                                   "grid_import_kw", "grid_export_kw")))
        check("extras present", all(k in t for k in ("grid_connected", "mode", "load_kw")))
        check("frequency ~ 50 Hz", 49.0 <= t["frequency"] <= 51.0, f"{t['frequency']}")
        check("starts grid-connected", t["grid_connected"] is True and t["mode"] == "grid_connected")

        # 2. set_setpoint -> PCC tracks setpoint while grid-connected
        check("set_setpoint ACKED",
              driver.execute_command("set_setpoint", {"setpoint_kw": 12.5}).status == "ACKED")
        time.sleep(0.3)
        ts = driver.normalize(driver.read_telemetry())
        print(f"  after setpoint: power_kw={ts['power_kw']} import={ts['grid_import_kw']}")
        check("PCC tracks setpoint (~12.5)", abs(ts["power_kw"] - 12.5) < 0.01, f"{ts['power_kw']}")
        check("grid_import mirrors +PCC", abs(ts["grid_import_kw"] - 12.5) < 0.01)

        # 3. island -> PCC collapses to 0, frequency droops off-nominal
        check("island ACKED", driver.execute_command("island", {}).status == "ACKED")
        time.sleep(0.3)
        ti = driver.normalize(driver.read_telemetry())
        print(f"  islanded: power_kw={ti['power_kw']} freq={ti['frequency']} mode={ti['mode']}")
        check("island -> mode islanded", ti["mode"] == "islanded", ti["mode"])
        check("island -> PCC 0", ti["power_kw"] == 0.0, f"{ti['power_kw']}")
        check("island -> frequency off-nominal (droop)", ti["frequency"] != 50.0, f"{ti['frequency']}")

        # 4. grid_connect -> back to grid-connected, PCC tracks setpoint again
        check("grid_connect ACKED", driver.execute_command("grid_connect", {}).status == "ACKED")
        time.sleep(0.3)
        tg = driver.normalize(driver.read_telemetry())
        print(f"  reconnected: power_kw={tg['power_kw']} mode={tg['mode']}")
        check("grid_connect -> grid_connected", tg["mode"] == "grid_connected", tg["mode"])
        check("PCC tracks setpoint again (~12.5)", abs(tg["power_kw"] - 12.5) < 0.01, f"{tg['power_kw']}")

        # 5. validation
        check("set_setpoint w/o param FAILED",
              driver.execute_command("set_setpoint", {}).status == "FAILED")
        check("unknown command FAILED", driver.execute_command("explode", {}).status == "FAILED")
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
