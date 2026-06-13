"""BACnet building-integration adapter.

STUB. NOTE: BACnet is NOT owned by any 9C–9G sub-phase (see
DIEP_PROTOCOL_ADAPTER_FRAMEWORK.md §5). Included in the tree per the 9B spec;
recommend scoping under smart-city / building integration or deferring.

Implementation TODO:
  - BACnet/IP (lib: BAC0 / bacpypes3); read present-value of analog/binary objects.
  - Map building meters/HVAC points -> telemetry; writable points -> commands.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register


@register("bacnet")
class BacnetDriver(BaseDriver):
    domain = "meter"

    def connect(self) -> None:
        raise NotImplementedError("BACnet not yet implemented (unscoped — see framework doc)")

    def read_telemetry(self) -> dict:
        raise NotImplementedError

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        return CommandResult("FAILED", f"unsupported command '{command_type}'")
