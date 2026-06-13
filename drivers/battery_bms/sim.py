"""Simulated battery / BMS — a Modbus TCP endpoint for testing 9D.

Serves the BMS register map over Modbus TCP so the BatteryBmsDriver can be driven
through onboarding -> certification and DERMS dispatch with no field hardware.
State of charge integrates from the commanded mode/power; the control registers
(cmd_mode, power_setpoint, target_soc, power_limit) are written by the driver and
honoured on the next read.

Sign convention (matches the driver/report): power_kw negative = charging,
positive = discharging.

Standalone:
    python -m battery_bms.sim --port 1702 --capacity 200 --soc 75    # from drivers/
"""
from __future__ import annotations

import sys
import time
import logging
import argparse

from . import models
from .transport import ModbusTcpServer

logger = logging.getLogger("diep-driver.battery_bms.sim")

NOMINAL_VOLTAGE = 700.0   # DC bus
AMBIENT_TEMP = 25.0
SOH = 98.0


class BatteryBmsSim:
    def __init__(self, capacity_kwh: float = 200.0, soc: float = 75.0,
                 base: int = models.DEFAULT_BASE, host: str = "127.0.0.1", port: int = 1702):
        self.capacity_kwh = capacity_kwh
        self.soc = soc
        self.base = base
        self.server = ModbusTcpServer(host=host, port=port, on_read=self._on_read)
        self._last = time.time()
        self.rm = models.REGISTER_MAP
        # Seed: standby, default setpoint/limit, target full.
        self._write_image(cmd_mode=models.CMD_STANDBY, setpoint=50.0,
                          target_soc=100, limit=100.0)

    # --- public ----------------------------------------------------------
    def start(self) -> int:
        port = self.server.start()
        logger.info("Battery BMS simulator serving on %s:%s (%.0f kWh, SoC %.1f%%)",
                    self.server.host, port, self.capacity_kwh, self.soc)
        return port

    def stop(self) -> None:
        self.server.stop()

    # --- control read-back -----------------------------------------------
    def _read_control(self):
        regs = self.server.registers
        rm = self.rm
        cmd_mode = regs.get(rm["cmd_mode"][0], models.CMD_STANDBY)
        sp_addr = rm["power_setpoint_kw"][0]
        setpoint = models._regs_to_f32(regs.get(sp_addr, 0), regs.get(sp_addr + 1, 0))
        target_soc = regs.get(rm["target_soc"][0], 100)
        lim_addr = rm["power_limit_kw"][0]
        limit = models._regs_to_f32(regs.get(lim_addr, 0), regs.get(lim_addr + 1, 0))
        return int(cmd_mode), float(setpoint), int(target_soc), float(limit)

    # --- integration + image ---------------------------------------------
    def _write_image(self, cmd_mode=None, setpoint=None, target_soc=None, limit=None):
        # When called from on_read, pull current control values; on seed, use args.
        if cmd_mode is None:
            cmd_mode, setpoint, target_soc, limit = self._read_control()

        now = time.time()
        dt_h = max(0.0, (now - self._last) / 3600.0)
        self._last = now

        eff_power = min(abs(setpoint), abs(limit)) if limit else abs(setpoint)
        delta_soc = eff_power * dt_h / self.capacity_kwh * 100.0 if self.capacity_kwh else 0.0

        # target_soc bounds the action: a ceiling for charge, a floor for discharge.
        # It only constrains when it lies in the direction of travel; otherwise the
        # natural limit (100% charge / 0% discharge) applies, so a bare charge/
        # discharge (no target) still runs while a DERMS target_soc is honoured.
        state = models.STATE_STANDBY
        power_kw = 0.0
        if cmd_mode == models.CMD_CHARGE:
            ceiling = target_soc if target_soc > self.soc else 100.0
            if self.soc < ceiling:
                self.soc = min(ceiling, self.soc + delta_soc)
                power_kw = -eff_power          # negative = charging
                state = models.STATE_CHARGING
        elif cmd_mode == models.CMD_DISCHARGE:
            floor = target_soc if target_soc < self.soc else 0.0
            if self.soc > floor:
                self.soc = max(floor, self.soc - delta_soc)
                power_kw = eff_power           # positive = discharging
                state = models.STATE_DISCHARGING
        # else: standby / target reached -> idle at 0 kW

        current = abs(power_kw) * 1000.0 / NOMINAL_VOLTAGE
        # Temperature rises a little under load.
        temperature = AMBIENT_TEMP + 3.0 + (eff_power / 100.0) * 4.0 if state != models.STATE_STANDBY \
            else AMBIENT_TEMP + 3.0

        values = {
            "battery_soc": round(self.soc, 3),
            "voltage": round(NOMINAL_VOLTAGE, 2),
            "current": round(current, 3),
            "power_kw": round(power_kw, 3),
            "temperature": round(temperature, 2),
            "soh": SOH,
            "state": state,
            # preserve control registers so driver writes are not clobbered:
            "cmd_mode": cmd_mode,
            "power_setpoint_kw": setpoint,
            "target_soc": target_soc,
            "power_limit_kw": limit,
        }
        base, regs = models.build_registers(values, base=self.base)
        self.server.set_registers(base, regs)

    def _on_read(self, server: ModbusTcpServer) -> None:
        self._write_image()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Battery BMS simulator (Modbus TCP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1702)
    parser.add_argument("--capacity", type=float, default=200.0, help="kWh")
    parser.add_argument("--soc", type=float, default=75.0, help="initial SoC %%")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    sim = BatteryBmsSim(capacity_kwh=args.capacity, soc=args.soc,
                        host=args.host, port=args.port)
    sim.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
        print("battery simulator stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
