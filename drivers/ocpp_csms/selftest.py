"""End-to-end selftest for the OCPP CSMS vertical against a simulated charge point.

No broker, no external deps: starts the CSMS core (transport+protocol, no MQTT) on
an ephemeral port, connects the OCPP charge-point simulator, and asserts canonical
telemetry from MeterValues plus the start/limit/stop command lifecycle over OCPP.

Run from drivers/:
    python -m ocpp_csms.selftest
"""
from __future__ import annotations

import sys
import time

from diep_driver import normalize_canonical
from ocpp_csms.driver import Csms
from ocpp_csms.sim import ChargePointSim


def main() -> int:
    failures = []
    latest = {}

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    def on_telemetry(charger_id, native):
        latest.clear()
        latest.update(native)

    csms = Csms(host="127.0.0.1", port=0, on_telemetry=on_telemetry)
    port = csms.start()
    print(f"CSMS on ws://127.0.0.1:{port}")

    cp = ChargePointSim("127.0.0.1", port, charger_id="EVSE900", max_power_kw=22.0, interval=0.4)
    try:
        cp.start()

        def wait_for(pred, timeout=6.0):
            t0 = time.time()
            while time.time() - t0 < timeout:
                if latest and pred(latest):
                    return True
                time.sleep(0.1)
            return False

        # 1. charge point connected + telemetry arriving
        check("charge point registered with CSMS",
              wait_for(lambda d: True) and "EVSE900" in csms.connected_chargers(),
              str(csms.connected_chargers()))
        canon = normalize_canonical(latest, aliases={})
        print(f"  idle telemetry: native={latest}")
        check("canonical voltage present", canon.get("voltage", 0) > 0, f"{canon.get('voltage')}")
        check("extras present (energy/soc)",
              "session_energy_kwh" in latest and "vehicle_soc" in latest)
        check("idle power is 0", latest.get("power_kw", 0) == 0, f"{latest.get('power_kw')}")

        # 2. start_charging -> RemoteStartTransaction -> power flows
        st, err = csms.send_command("EVSE900", "start_charging", {"max_power_kw": 22})
        check("start_charging ACKED", st == "ACKED", err or "")
        check("charging -> power > 0", wait_for(lambda d: d.get("power_kw", 0) > 0),
              f"{latest.get('power_kw')}")
        print(f"  charging telemetry: power={latest.get('power_kw')} status={latest.get('connector_status')}")
        check("connector status Charging", latest.get("connector_status") == "Charging",
              str(latest.get("connector_status")))

        # 3. set_limit -> SetChargingProfile -> power capped
        st, err = csms.send_command("EVSE900", "set_limit", {"max_power_kw": 5})
        check("set_limit ACKED", st == "ACKED", err or "")
        time.sleep(1.0)
        check("power capped at ~5 kW", latest.get("power_kw", 99) <= 5.2, f"{latest.get('power_kw')}")

        # 4. stop_charging -> RemoteStopTransaction -> power 0
        st, err = csms.send_command("EVSE900", "stop_charging", {})
        check("stop_charging ACKED", st == "ACKED", err or "")
        check("stopped -> power 0", wait_for(lambda d: d.get("power_kw", 1) == 0),
              f"{latest.get('power_kw')}")

        # 5. validation
        st, _ = csms.send_command("EVSE900", "set_limit", {})  # missing param
        check("set_limit w/o param FAILED", st == "FAILED")
        st, _ = csms.send_command("EVSE900", "explode", {})
        check("unknown command FAILED", st == "FAILED")
        st, _ = csms.send_command("GHOST", "start_charging", {})
        check("command to absent charger FAILED", st == "FAILED")
    finally:
        cp.stop()
        csms.stop()

    print()
    if failures:
        print(f"SELFTEST FAILED ({len(failures)} check(s)): {failures}")
        return 1
    print("SELFTEST PASSED — all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
