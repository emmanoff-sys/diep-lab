"""End-to-end selftest for the SunSpec driver against the bundled simulator.

No field hardware, no broker, no extra deps: starts the Modbus-TCP SunSpec
simulator on an ephemeral port, runs the real SunSpecDriver against it, and
asserts canonical telemetry + curtailment behaviour.

Run from drivers/:
    python -m sunspec.selftest
"""
from __future__ import annotations

import sys
import time
import threading

from sunspec.sim import SunSpecInverterSim
from sunspec.driver import SunSpecDriver
from sunspec.transport import _BuiltinModbusClient, ModbusTcpServer


def _read_nonzero(driver, attempts=40, sleep=0.25):
    """Read telemetry until the synthetic day yields production (or give up)."""
    last = {}
    for _ in range(attempts):
        last = driver.normalize(driver.read_telemetry())
        if last.get("power_kw", 0) > 0:
            return last
        time.sleep(sleep)
    return last


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    # Long day + noon start so irradiance is near-steady during the test window,
    # making before/after curtailment readings directly comparable.
    sim = SunSpecInverterSim(capacity_kw=10.0, day_period_s=3600.0, noon_start=True, port=0)
    port = sim.start()
    print(f"simulator on 127.0.0.1:{port}")

    driver = SunSpecDriver("INV900", {"host": "127.0.0.1", "port": port, "capacity_kw": 10.0})
    try:
        # 1. connect + model discovery
        driver.connect()
        check("connect discovers SunSpec models", set(driver.models) >= {1, 103, 123},
              f"models={sorted(driver.models)}")

        # 2. telemetry decode -> canonical schema
        t = _read_nonzero(driver)
        print(f"  telemetry: {t}")
        check("canonical fields present",
              all(k in t for k in ("voltage", "current", "power_kw", "frequency",
                                   "solar_kw", "battery_soc", "grid_import_kw", "grid_export_kw")))
        check("frequency ~ 50 Hz", 49.0 <= t.get("frequency", 0) <= 51.0, f"{t.get('frequency')}")
        check("voltage ~ 230 V", 220.0 <= t.get("voltage", 0) <= 240.0, f"{t.get('voltage')}")
        check("power within capacity", 0 < t.get("power_kw", -1) <= 10.0, f"{t.get('power_kw')} kW")
        check("solar_kw >= power_kw (DC>=AC)", t.get("solar_kw", 0) >= t.get("power_kw", 0))
        check("grid_export mirrors production",
              abs(t.get("grid_export_kw", 0) - t.get("power_kw", 0)) < 1e-6)

        # 3. curtail to 30% -> power should drop materially
        before = _read_nonzero(driver)["power_kw"]
        res = driver.execute_command("curtail", {"limit_kw": 3.0})
        check("curtail ACKED", res.status == "ACKED", res.error or "")
        time.sleep(0.3)
        after = driver.normalize(driver.read_telemetry())["power_kw"]
        print(f"  power before curtail={before:.3f} kW, after={after:.3f} kW")
        check("curtail reduced power", after < before, f"{after:.3f} < {before:.3f}")
        check("curtail respects ~3 kW cap", after <= 3.05, f"{after:.3f} kW")

        # 4. resume -> power recovers toward available
        driver.execute_command("resume", {})
        time.sleep(0.3)
        recovered = driver.normalize(driver.read_telemetry())["power_kw"]
        print(f"  power after resume={recovered:.3f} kW")
        check("resume lifts the cap", recovered > after, f"{recovered:.3f} > {after:.3f}")

        # 5. command validation
        bad = driver.execute_command("set_limit", {})  # missing max_power_kw
        check("set_limit without param FAILED", bad.status == "FAILED", bad.error or "")
        unknown = driver.execute_command("explode", {})
        check("unknown command FAILED", unknown.status == "FAILED", unknown.error or "")
    finally:
        driver.disconnect()
        sim.stop()

    # 6. concurrent transactions on a shared client (BAT001 regression — Runner's
    #    telemetry-poll thread and MQTT command-callback thread share one
    #    _BuiltinModbusClient; their _txn() calls must not interleave on the socket).
    print("\nconcurrency: shared-client read/write from two threads")
    srv = ModbusTcpServer(port=0)
    srv.set_registers(4000, [0] * 19)
    port = srv.start()
    client = _BuiltinModbusClient("127.0.0.1", port, unit=1, timeout=5.0)
    client.connect()
    try:
        errors: list[tuple[str, int, str]] = []

        def reader():
            for i in range(50):
                try:
                    client.read_holding(4000, 19)
                except Exception as exc:  # noqa: BLE001
                    errors.append(("read", i, str(exc)))

        def writer():
            for i in range(50):
                try:
                    client.write_registers(4000, [1])
                except Exception as exc:  # noqa: BLE001
                    errors.append(("write", i, str(exc)))

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start(); t2.start()
        t1.join(); t2.join()
        check("concurrent read/write: no transaction id mismatch", not errors,
              f"{len(errors)} error(s), e.g. {errors[:3]}")
    finally:
        client.close()
        srv.stop()

    print()
    if failures:
        print(f"SELFTEST FAILED ({len(failures)} check(s)): {failures}")
        return 1
    print("SELFTEST PASSED — all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
