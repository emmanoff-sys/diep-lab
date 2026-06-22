"""Mock DNP3 outstation — an in-process RTU point database for testing.

Stands in for a real DNP3 outstation (no opendnp3/pydnp3 dependency): holds the
point database from models.py, evolves the measurements over time with simple
microgrid physics, and applies control operations (breaker trip/close, PCC
setpoint). The Dnp3Driver polls/operates this instead of field hardware.
"""
from __future__ import annotations

import math
import time

from . import models


class MockDnp3Outstation:
    def __init__(self, nominal_freq: float = models.NOMINAL_HZ,
                 droop_kw_per_hz: float = 20.0, period_s: float = 60.0):
        self.nominal_freq = nominal_freq
        self.droop = droop_kw_per_hz
        self.period_s = period_s
        self._t0 = time.time()
        # control state
        self.grid_connected = True
        self.setpoint_kw = 0.0
        # latest computed measurements
        self._ai = {}
        self._evolve()

    # --- transport lifecycle (in-process; conforms to the Dnp3Transport API) --
    def connect(self) -> None:
        """No link to open — the outstation lives in-process."""

    def close(self) -> None:
        """No link to close."""

    # --- master-facing reads ---------------------------------------------
    def read_analog(self, index: int) -> float:
        self._evolve()
        return self._ai.get(index, 0.0)

    def read_binary(self, index: int) -> int:
        if index == models.BI_GRID_CONNECTED:
            return 1 if self.grid_connected else 0
        return 0

    def read_setpoint(self) -> float:
        """Last latched analog-output (PCC) setpoint — for command-echo (P3-2)."""
        return float(self.setpoint_kw)

    # --- master-facing controls (return True on success) ------------------
    def operate_binary(self, index: int, value: int) -> bool:
        if index == models.BO_BREAKER:
            self.grid_connected = bool(value)
            return True
        return False

    def operate_analog(self, index: int, value: float) -> bool:
        if index == models.AO_SETPOINT_KW:
            self.setpoint_kw = float(value)
            return True
        return False

    # --- physics ----------------------------------------------------------
    def _evolve(self) -> None:
        phase = ((time.time() - self._t0) % self.period_s) / self.period_s * 2 * math.pi
        load = 8.0 + 3.0 * (1 + math.sin(phase)) / 2 * 2          # ~8..14 kW
        solar = max(0.0, 6.0 * math.sin(phase))                   # 0..6 kW
        net = load - solar
        if self.grid_connected:
            pcc = self.setpoint_kw if self.setpoint_kw else net   # import to cover net load
            freq = self.nominal_freq + 0.02 * math.sin(phase * 3)
        else:
            pcc = 0.0                                             # islanded: no PCC exchange
            freq = self.nominal_freq - net / self.droop           # droop response
        self._ai = {
            models.AI_VOLTAGE: round(models.NOMINAL_VOLTAGE + 3 * math.sin(phase), 2),
            models.AI_FREQUENCY: round(freq, 3),
            models.AI_PCC_KW: round(pcc, 3),
            models.AI_LOAD_KW: round(load, 3),
            models.AI_SOLAR_KW: round(solar, 3),
        }
