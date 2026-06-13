"""Modbus TCP/RTU adapter (Phase 9C smart meters, 9D battery, 9E solar, 9G microgrid).

STUB. Implementation TODO (Wave 2/3):
  - Use `pymodbus` for the transport (TCP:502 or serial RTU).
  - Express per-vendor register maps as DATA (YAML/JSON), not code:
      {"power_kw": {"reg": 40097, "type": "int32", "scale": 0.001}, ...}
  - read_telemetry(): read the register block, decode per the map.
  - execute_command(): write holding registers / coils per the command map.
Vendors: Landis+Gyr, Itron, Hexing, EDMI, Huawei, Schneider (smart meters);
also generic battery/solar/microgrid Modbus profiles.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register


@register("modbus")
class ModbusMeterDriver(BaseDriver):
    domain = "meter"
    # Native register-map keys → canonical fields (example for a meter profile).
    aliases = {"V": "voltage", "I": "current", "P_kw": "power_kw", "Hz": "frequency"}

    def connect(self) -> None:
        # TODO: from pymodbus.client import ModbusTcpClient; self.client = ...
        raise NotImplementedError("Modbus transport not yet implemented (Wave 2)")

    def read_telemetry(self) -> dict:
        # TODO: read register block, decode via the vendor register map.
        raise NotImplementedError

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        # Meters are typically read-only; battery/solar profiles write registers.
        return CommandResult("FAILED", f"unsupported command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return set()
