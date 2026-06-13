"""Simulated SunSpec PV inverter — a Modbus TCP endpoint for testing 9E.

Serves a real SunSpec register image (common + inverter 103 + controls 123) over
Modbus TCP so the SunSpecDriver can be exercised through onboarding -> certification
with no field hardware. Output follows a synthetic irradiance curve and honors
WMaxLimPct/WMaxLim_Ena writes from the driver (curtailment actually reduces power).

Standalone:
    python -m sunspec.sim --port 1502 --capacity 10        # from drivers/
Then point a driver/edge-agent at host=127.0.0.1, port=1502.
"""
from __future__ import annotations

import sys
import time
import math
import logging
import argparse

from . import models
from .transport import ModbusTcpServer

logger = logging.getLogger("diep-driver.sunspec.sim")

NOMINAL_VOLTAGE = 230.0
NOMINAL_HZ = 50.0
DC_EFFICIENCY = 0.97  # AC = DC * efficiency; so DC power is slightly higher


class SunSpecInverterSim:
    def __init__(self, capacity_kw: float = 10.0, base: int = models.DEFAULT_BASE,
                 day_period_s: float = 120.0, host: str = "127.0.0.1", port: int = 1502,
                 noon_start: bool = False):
        self.capacity_kw = capacity_kw
        self.base = base
        self.day_period_s = day_period_s
        self.server = ModbusTcpServer(host=host, port=port, on_read=self._on_read)
        # noon_start places "now" at the irradiance peak (phase pi/2) so output is
        # near-steady — useful for deterministic tests; default begins at sunrise.
        self._t0 = time.time() - (day_period_s / 4.0 if noon_start else 0.0)

        # Seed an initial image, then locate the control registers so reads can
        # preserve driver-written curtailment instead of overwriting it.
        self._write_image(wmaxlimpct=100.0, wmaxlim_ena=0)
        locs = models.discover(self._read_local, base=self.base)
        ctl = locs[123]
        pts = models.CONTROLS_MODEL_123["points"]
        self.pct_addr = ctl.data_addr + pts["WMaxLimPct"][0]
        self.ena_addr = ctl.data_addr + pts["WMaxLim_Ena"][0]

    # --- public ----------------------------------------------------------
    def start(self) -> int:
        port = self.server.start()
        logger.info("SunSpec simulator serving on %s:%s (capacity %.1f kW)",
                    self.server.host, port, self.capacity_kw)
        return port

    def stop(self) -> None:
        self.server.stop()

    # --- register plumbing -----------------------------------------------
    def _read_local(self, addr: int, count: int) -> list[int]:
        return [self.server.registers.get(addr + i, 0) for i in range(count)]

    def available_kw(self) -> float:
        """Synthetic array potential from a half-sine 'day' (sunrise..sunset)."""
        phase = ((time.time() - self._t0) % self.day_period_s) / self.day_period_s * math.pi
        return self.capacity_kw * max(0.0, math.sin(phase))

    def _write_image(self, wmaxlimpct: float, wmaxlim_ena: int) -> None:
        available = self.available_kw()
        # WMaxLimPct caps active power at a percentage of *rated* power (WMax),
        # so the inverter produces min(available, capacity * pct%).
        if wmaxlim_ena:
            cap_kw = self.capacity_kw * (wmaxlimpct / 100.0)
            limited = min(available, cap_kw)
        else:
            limited = available
        ac_w = int(round(limited * 1000))
        dc_w = int(round(ac_w / DC_EFFICIENCY)) if ac_w > 0 else 0
        current_a = ac_w / NOMINAL_VOLTAGE if NOMINAL_VOLTAGE else 0.0

        if ac_w <= 0:
            state = models.ST_SLEEPING
        elif wmaxlim_ena and wmaxlimpct < 100.0:
            state = models.ST_THROTTLED
        else:
            state = models.ST_MPPT

        base, regs = models.build_image(
            ac_w=ac_w, dc_w=dc_w, voltage_v=NOMINAL_VOLTAGE, current_a=current_a,
            hz=NOMINAL_HZ, state=state, wmax_w=int(self.capacity_kw * 1000),
            wmaxlimpct=wmaxlimpct, wmaxlim_ena=wmaxlim_ena, base=self.base,
        )
        self.server.set_registers(base, regs)

    def _on_read(self, server: ModbusTcpServer) -> None:
        # Preserve any curtailment the driver wrote, then refresh telemetry.
        pct = server.registers.get(self.pct_addr, 100)
        ena = server.registers.get(self.ena_addr, 0)
        self._write_image(wmaxlimpct=float(pct), wmaxlim_ena=int(ena))


def main(argv=None):
    parser = argparse.ArgumentParser(description="SunSpec PV inverter simulator (Modbus TCP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1502)
    parser.add_argument("--capacity", type=float, default=10.0, help="rated kW")
    parser.add_argument("--day-period", type=float, default=120.0,
                        help="seconds for one synthetic sunrise..sunset")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    sim = SunSpecInverterSim(capacity_kw=args.capacity, day_period_s=args.day_period,
                             host=args.host, port=args.port)
    sim.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
        print("simulator stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
