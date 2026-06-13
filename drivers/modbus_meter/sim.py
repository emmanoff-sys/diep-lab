"""Simulated Modbus smart meter — a Modbus TCP endpoint for testing 9C.

Serves the meter register map over Modbus TCP so the ModbusMeterDriver can be
exercised through onboarding -> certification with no field hardware. Measurements
follow a smooth load profile, energy counters accumulate over time, and the
control relay honours remote_disconnect/remote_connect writes (when disconnected,
power/current collapse to zero and the energy counters freeze).

Standalone:
    python -m modbus_meter.sim --port 1602 --base-load 3.5      # from drivers/
"""
from __future__ import annotations

import sys
import time
import math
import logging
import argparse

from . import models
from .transport import ModbusTcpServer

logger = logging.getLogger("diep-driver.modbus_meter.sim")

NOMINAL_VOLTAGE = 230.0
NOMINAL_HZ = 50.0
POWER_FACTOR = 0.98


class ModbusMeterSim:
    def __init__(self, base_load_kw: float = 3.5, swing_kw: float = 1.5,
                 period_s: float = 60.0, base: int = models.DEFAULT_BASE,
                 host: str = "127.0.0.1", port: int = 1602,
                 energy_import_kwh: float = 1000.0, energy_export_kwh: float = 200.0):
        self.base_load_kw = base_load_kw
        self.swing_kw = swing_kw
        self.period_s = period_s
        self.base = base
        self.server = ModbusTcpServer(host=host, port=port, on_read=self._on_read)
        self._t0 = time.time()
        self._last = self._t0
        self.energy_import = energy_import_kwh
        self.energy_export = energy_export_kwh
        self.relay_addr = models.REGISTER_MAP["relay_state"][0]
        # Seed an initial image (relay connected).
        self._write_image(relay=models.RELAY_CONNECTED)

    # --- public ----------------------------------------------------------
    def start(self) -> int:
        port = self.server.start()
        logger.info("Modbus meter simulator serving on %s:%s (base load %.1f kW)",
                    self.server.host, port, self.base_load_kw)
        return port

    def stop(self) -> None:
        self.server.stop()

    # --- register plumbing -----------------------------------------------
    def _load_kw(self) -> float:
        phase = ((time.time() - self._t0) % self.period_s) / self.period_s * 2 * math.pi
        return max(0.0, self.base_load_kw + self.swing_kw * math.sin(phase))

    def _write_image(self, relay: int) -> None:
        now = time.time()
        dt_h = max(0.0, (now - self._last) / 3600.0)
        self._last = now

        connected = relay == models.RELAY_CONNECTED
        power_kw = self._load_kw() if connected else 0.0
        if connected:
            self.energy_import += power_kw * dt_h  # accumulate consumed energy

        current = (power_kw * 1000.0) / (NOMINAL_VOLTAGE * POWER_FACTOR) if connected else 0.0
        values = {
            "voltage": NOMINAL_VOLTAGE if connected else 0.0,
            "current": round(current, 3),
            "power_kw": round(power_kw, 3),
            "frequency": NOMINAL_HZ if connected else 0.0,
            "power_factor": POWER_FACTOR if connected else 0.0,
            "energy_import_kwh": round(self.energy_import, 4),
            "energy_export_kwh": round(self.energy_export, 4),
            "relay_state": relay,
        }
        base, regs = models.build_registers(values, base=self.base)
        self.server.set_registers(base, regs)

    def _on_read(self, server: ModbusTcpServer) -> None:
        # Preserve any relay state the driver wrote, then refresh measurements.
        relay = server.registers.get(self.relay_addr, models.RELAY_CONNECTED)
        self._write_image(relay=int(relay))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Modbus smart-meter simulator (Modbus TCP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1602)
    parser.add_argument("--base-load", type=float, default=3.5, help="mean load kW")
    parser.add_argument("--swing", type=float, default=1.5, help="load swing kW")
    parser.add_argument("--period", type=float, default=60.0, help="load cycle seconds")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    sim = ModbusMeterSim(base_load_kw=args.base_load, swing_kw=args.swing,
                         period_s=args.period, host=args.host, port=args.port)
    sim.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
        print("meter simulator stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
