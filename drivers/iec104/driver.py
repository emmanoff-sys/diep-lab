"""IEC 60870-5-104 microgrid/RTU adapter (Phase 9G).

STUB. Implementation TODO (Wave 3):
  - TCP client (port 2404) to the RTU/controller; handle ASDU types.
  - Map monitored points (M_ME_NC_1 measured float, M_SP_NA_1 single point) ->
    canonical telemetry (frequency, power_kw, grid import/export).
  - Commands via C_SC_NA_1 (single command) / C_SE_NC_1 (setpoint) for
    island / grid_connect / load shedding / frequency support.
Vendors: Schneider EcoStruxure, Siemens, ABB, SEL. Lib: c104.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register


@register("iec104")
class Iec104Driver(BaseDriver):
    domain = "microgrid"
    aliases = {"freq_hz": "frequency", "pcc_kw": "power_kw"}

    def connect(self) -> None:
        raise NotImplementedError("IEC 60870-5-104 client not yet implemented (Wave 3)")

    def read_telemetry(self) -> dict:
        raise NotImplementedError

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")
        raise NotImplementedError

    def supported_commands(self) -> set[str]:
        return {"island", "grid_connect", "set_setpoint"}
