"""SunSpec-over-Modbus adapter (Phase 9E solar).

SunSpec standardizes register models across Huawei/Sungrow/SMA/Fronius/Solis, so a
single driver covers most PV inverters with minimal per-vendor work. This driver:

  - connect():        open Modbus TCP and discover the device's SunSpec models;
  - read_telemetry(): read inverter model 103, decode to canonical solar telemetry;
  - execute_command(): curtail / set_limit / resume via controls model 123
                       (WMaxLimPct + WMaxLim_Ena).

Transport is `pymodbus` on the edge gateway, or a built-in Modbus client elsewhere
(see transport.open_modbus). Decoding is in `models` (dependency-free), so the same
driver works against a real inverter or the bundled simulator (sim.py).

Config keys: host, port (default 502), unit (default 1), base (default 40000),
capacity_kw (rated WMax, used to translate kW limits into WMaxLimPct).
"""
from __future__ import annotations

import logging

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .transport import open_modbus

logger = logging.getLogger("diep-driver.sunspec")


@register("sunspec")
class SunSpecDriver(BaseDriver):
    domain = "solar"
    # Native (already-scaled) keys -> canonical fields. voltage/current pass through
    # by name; W_kw/Hz/DCW_kw are produced in canonical units by read_telemetry().
    aliases = {"W_kw": "power_kw", "Hz": "frequency", "DCW_kw": "solar_kw", "ChaState": "battery_soc"}

    def __init__(self, device_id: str, config: dict | None = None):
        super().__init__(device_id, config)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 502))
        self.unit = int(self.config.get("unit", 1))
        self.base = int(self.config.get("base", models.DEFAULT_BASE))
        self.capacity_kw = float(self.config.get("capacity_kw", 10.0))
        self.client = None
        self.models: dict[int, models.ModelLocation] = {}

    # --- protocol session -------------------------------------------------
    def connect(self) -> None:
        if self.client is None:
            self.client = open_modbus(self.host, self.port, self.unit,
                                      timeout=float(self.config.get("timeout", 5.0)))
        self.models = models.discover(self.client.read_holding, base=self.base)
        if models.INVERTER_MODEL_103["id"] not in self.models:
            raise RuntimeError(
                f"{self.device_id}: device exposes no inverter model 103 "
                f"(found models {sorted(self.models)})"
            )
        logger.info("%s connected to %s:%s; models=%s",
                    self.device_id, self.host, self.port, sorted(self.models))

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    # --- telemetry --------------------------------------------------------
    def read_telemetry(self) -> dict:
        loc = self.models[models.INVERTER_MODEL_103["id"]]
        data = self.client.read_holding(loc.data_addr, loc.length)
        decoded = models.decode_model(models.INVERTER_MODEL_103, data)
        native = {
            "voltage": decoded.get("PhVphA", 0.0),
            "current": decoded.get("A", 0.0),
            "W_kw": decoded.get("W", 0.0) / 1000.0,      # AC active power -> kW
            "Hz": decoded.get("Hz", 0.0),
            "DCW_kw": decoded.get("DCW", 0.0) / 1000.0,  # DC/PV power -> kW
            "operating_state": decoded.get("St", 0),
        }
        # Storage model 802 (hybrid inverters) -> battery_soc, if exposed.
        # The PV simulator omits it; decoded here as Phase 9D battery groundwork.
        if 802 in self.models:
            loc802 = self.models[802]
            data802 = self.client.read_holding(loc802.data_addr, loc802.length)
            if hasattr(models, "STORAGE_MODEL_802"):
                soc = models.decode_model(models.STORAGE_MODEL_802, data802)
                native["ChaState"] = soc.get("ChaState", 0.0)
        return native

    def normalize(self, native: dict) -> dict:
        canonical = super().normalize(native)
        # A grid-tied PV inverter exports its production; mirror the platform's
        # solar semantics (ingestor maps solar output -> grid_export_kw).
        canonical["grid_export_kw"] = max(0.0, canonical.get("power_kw", 0.0))
        return canonical

    # --- commands ---------------------------------------------------------
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")
        if 123 not in self.models:
            return CommandResult("FAILED", "device exposes no controls model 123")

        if command_type == "resume":
            return self._set_limit_pct(100.0, enable=False)

        if command_type == "set_limit":
            if "max_power_kw" not in params:
                return CommandResult("FAILED", "set_limit requires params.max_power_kw")
            pct = self._kw_to_pct(float(params["max_power_kw"]))
            return self._set_limit_pct(pct, enable=True)

        if command_type == "curtail":
            limit_kw = float(params.get("limit_kw", self.capacity_kw * 0.5))
            pct = self._kw_to_pct(limit_kw)
            return self._set_limit_pct(pct, enable=True)

        return CommandResult("FAILED", f"unhandled command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return {"curtail", "set_limit", "resume"}

    # --- command helpers --------------------------------------------------
    def _kw_to_pct(self, kw: float) -> float:
        if self.capacity_kw <= 0:
            return 100.0
        return max(0.0, min(100.0, kw / self.capacity_kw * 100.0))

    def _set_limit_pct(self, pct: float, enable: bool) -> CommandResult:
        loc = self.models[123]
        ctl = models.CONTROLS_MODEL_123["points"]
        pct_off = ctl["WMaxLimPct"][0]
        ena_off = ctl["WMaxLim_Ena"][0]
        try:
            self.client.write_registers(loc.data_addr + pct_off, [int(round(pct))])
            self.client.write_registers(loc.data_addr + ena_off, [1 if enable else 0])
        except Exception as exc:  # noqa: BLE001 — surface as FAILED ack
            return CommandResult("FAILED", f"register write failed: {exc}")
        logger.info("%s set WMaxLimPct=%.0f%% ena=%s", self.device_id, pct, enable)
        return CommandResult("ACKED", None)
