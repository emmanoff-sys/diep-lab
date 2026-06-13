"""Battery / BMS Modbus adapter (Phase 9D).

The storage vertical, built on the same SDK + Modbus transport as the SunSpec
inverter (9E) and the smart meter (9C). It:

  - connect():        open Modbus TCP and probe the register block;
  - read_telemetry(): read the BMS register map, decode to canonical telemetry
                      (battery_soc, power_kw, voltage, current) plus extras
                      (temperature, soh, state);
  - execute_command(): charge / discharge / standby / idle / set_power_limit /
                       set_soc_target via the writable control registers.

domain = "battery" so telemetry (diep/battery/<id>) and the dispatcher command
topic (diep/battery/<id>/cmd) line up with the existing DOMAIN_MAP — and DERMS
(which dispatches charge/discharge/idle to batteries) actuates this driver
unchanged.

Config keys: host, port (default 502), unit (default 1), base (default 4000),
default_power_kw (used when a command omits a power value).
"""
from __future__ import annotations

import logging

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .transport import open_modbus

logger = logging.getLogger("diep-driver.battery_bms")


@register("battery_bms")
class BatteryBmsDriver(BaseDriver):
    domain = "battery"
    aliases = {}

    def __init__(self, device_id: str, config: dict | None = None):
        super().__init__(device_id, config)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 502))
        self.unit = int(self.config.get("unit", 1))
        self.base = int(self.config.get("base", models.DEFAULT_BASE))
        self.default_power_kw = float(self.config.get("default_power_kw", 50.0))
        self.client = None

    # --- protocol session -------------------------------------------------
    def connect(self) -> None:
        if self.client is None:
            self.client = open_modbus(self.host, self.port, self.unit,
                                      timeout=float(self.config.get("timeout", 5.0)))
        self.client.read_holding(self.base, models.BLOCK_LENGTH)  # probe / fail fast
        logger.info("%s connected to %s:%s (BMS register block @ %d)",
                    self.device_id, self.host, self.port, self.base)

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    # --- telemetry --------------------------------------------------------
    def read_telemetry(self) -> dict:
        regs = self.client.read_holding(self.base, models.BLOCK_LENGTH)
        b = models.decode_registers(regs, base=self.base)
        return {
            "battery_soc": b["battery_soc"],
            "voltage": b["voltage"],
            "current": b["current"],
            "power_kw": b["power_kw"],
            # extras (carried in the MQTT payload / twin):
            "temperature": b["temperature"],
            "soh": b["soh"],
            "state": models.STATE_NAMES.get(int(b["state"]), "UNKNOWN"),
        }

    def normalize(self, native: dict) -> dict:
        canonical = super().normalize(native)  # battery_soc/voltage/current/power_kw
        for k in ("temperature", "soh", "state"):
            if k in native:
                canonical[k] = native[k]
        # `mode` mirrors `state` for twin/headline consumers expecting either key.
        if "state" in native:
            canonical["mode"] = native["state"]
        return canonical

    # --- commands ---------------------------------------------------------
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")

        if command_type in ("standby", "idle"):
            return self._write_control(mode=models.CMD_STANDBY)

        if command_type == "set_power_limit":
            limit = params.get("power_kw", params.get("limit_kw", params.get("max_power_kw")))
            if limit is None:
                return CommandResult("FAILED", "set_power_limit requires params.power_kw")
            return self._write_control(power_limit_kw=float(limit))

        if command_type == "set_soc_target":
            target = params.get("soc_target", params.get("target_soc"))
            if target is None:
                return CommandResult("FAILED", "set_soc_target requires params.soc_target")
            return self._write_control(target_soc=int(round(float(target))))

        if command_type in ("charge", "discharge"):
            mode = models.CMD_CHARGE if command_type == "charge" else models.CMD_DISCHARGE
            # DERMS passes max_power_kw; a direct call may pass power_kw. Either works.
            power = params.get("power_kw", params.get("max_power_kw", self.default_power_kw))
            target = params.get("target_soc", params.get("soc_target"))
            return self._write_control(
                mode=mode,
                power_setpoint_kw=float(power),
                target_soc=int(round(float(target))) if target is not None else None,
            )

        return CommandResult("FAILED", f"unhandled command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return {"charge", "discharge", "standby", "idle", "set_power_limit", "set_soc_target"}

    # --- control register writes -----------------------------------------
    def _write_control(self, mode: int | None = None, power_setpoint_kw: float | None = None,
                       target_soc: int | None = None, power_limit_kw: float | None = None
                       ) -> CommandResult:
        rm = models.REGISTER_MAP
        try:
            if mode is not None:
                self.client.write_registers(rm["cmd_mode"][0], [int(mode) & 0xFFFF])
            if power_setpoint_kw is not None:
                self.client.write_registers(rm["power_setpoint_kw"][0],
                                            models._f32_to_regs(power_setpoint_kw))
            if target_soc is not None:
                self.client.write_registers(rm["target_soc"][0], [int(target_soc) & 0xFFFF])
            if power_limit_kw is not None:
                self.client.write_registers(rm["power_limit_kw"][0],
                                            models._f32_to_regs(power_limit_kw))
        except Exception as exc:  # noqa: BLE001 — surface as FAILED ack
            return CommandResult("FAILED", f"control write failed: {exc}")
        logger.info("%s control write mode=%s power=%s target_soc=%s limit=%s",
                    self.device_id, mode, power_setpoint_kw, target_soc, power_limit_kw)
        return CommandResult("ACKED", None)
