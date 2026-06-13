"""Modbus smart-meter adapter (Phase 9C).

The first real metering driver, built on the same SDK + Modbus transport as the
SunSpec inverter (9E). It:

  - connect():        open Modbus TCP and probe the register block;
  - read_telemetry(): read the meter register map, decode to canonical telemetry
                      plus meter-specific extras (power_factor, energy counters);
  - execute_command(): read_only / remote_disconnect / remote_connect via the
                       control relay register.

domain = "smartmeter" so telemetry (diep/smartmeter/<id>) and the dispatcher's
command topic (diep/<domain>/<id>/cmd, domain = device_type fallback) line up
without touching the dispatcher's DOMAIN_MAP.

Config keys: host, port (default 502), unit (default 1), base (default 3000).
"""
from __future__ import annotations

import logging

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .transport import open_modbus

logger = logging.getLogger("diep-driver.modbus_meter")


@register("modbus_meter")
class ModbusMeterDriver(BaseDriver):
    domain = "smartmeter"
    # voltage/current/frequency/power_kw pass through by canonical name; meter
    # extras and grid split are handled in normalize().
    aliases = {}

    def __init__(self, device_id: str, config: dict | None = None):
        super().__init__(device_id, config)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 502))
        self.unit = int(self.config.get("unit", 1))
        self.base = int(self.config.get("base", models.DEFAULT_BASE))
        self.client = None
        self._read_only = False

    # --- protocol session -------------------------------------------------
    def connect(self) -> None:
        if self.client is None:
            self.client = open_modbus(self.host, self.port, self.unit,
                                      timeout=float(self.config.get("timeout", 5.0)))
        # Probe the block so connect() fails fast on a wrong map/endpoint.
        self.client.read_holding(self.base, models.BLOCK_LENGTH)
        logger.info("%s connected to %s:%s (meter register block @ %d)",
                    self.device_id, self.host, self.port, self.base)

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    # --- telemetry --------------------------------------------------------
    def read_telemetry(self) -> dict:
        regs = self.client.read_holding(self.base, models.BLOCK_LENGTH)
        m = models.decode_registers(regs, base=self.base)
        return {
            "voltage": m["voltage"],
            "current": m["current"],
            "power_kw": m["power_kw"],
            "frequency": m["frequency"],
            # meter-specific extras (carried in the MQTT payload):
            "power_factor": m["power_factor"],
            "energy_import_kwh": m["energy_import_kwh"],
            "energy_export_kwh": m["energy_export_kwh"],
            "relay_state": m["relay_state"],
        }

    def normalize(self, native: dict) -> dict:
        canonical = super().normalize(native)  # voltage/current/power_kw/frequency
        # A revenue meter measures the grid connection: split signed active power
        # into import/export so the platform's grid fields reflect real flow.
        p = canonical.get("power_kw", 0.0)
        canonical["grid_import_kw"] = max(0.0, p)
        canonical["grid_export_kw"] = max(0.0, -p)
        # Carry meter-only fields for the twin / future schema (not in the 8-field
        # canonical core; persisted only where the consumer accepts them).
        for k in ("power_factor", "energy_import_kwh", "energy_export_kwh", "relay_state"):
            if k in native:
                canonical[k] = native[k]
        return canonical

    # --- commands ---------------------------------------------------------
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")

        if command_type == "read_only":
            # Latch the meter to read-only: refuse subsequent actuation until reset.
            self._read_only = True
            logger.info("%s set to read_only mode", self.device_id)
            return CommandResult("ACKED", None)

        if self._read_only:
            return CommandResult("FAILED", "meter is in read_only mode; actuation disabled")

        if command_type == "remote_disconnect":
            return self._set_relay(models.RELAY_DISCONNECTED)
        if command_type == "remote_connect":
            return self._set_relay(models.RELAY_CONNECTED)

        return CommandResult("FAILED", f"unhandled command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return {"read_only", "remote_disconnect", "remote_connect"}

    # --- command helpers --------------------------------------------------
    def _set_relay(self, state: int) -> CommandResult:
        addr = models.REGISTER_MAP["relay_state"][0]
        try:
            self.client.write_registers(addr, [int(state) & 0xFFFF])
        except Exception as exc:  # noqa: BLE001 — surface as FAILED ack
            return CommandResult("FAILED", f"relay write failed: {exc}")
        logger.info("%s relay -> %s", self.device_id,
                    "CONNECTED" if state == models.RELAY_CONNECTED else "DISCONNECTED")
        return CommandResult("ACKED", None)
