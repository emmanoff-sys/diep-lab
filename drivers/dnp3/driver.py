"""DNP3 outstation adapter (common in utility RTUs).

STUB. Implementation TODO:
  - DNP3 master polling an outstation (lib: dnp3-python / pydnp3 / opendnp3).
  - Map analog inputs -> telemetry; binary/analog outputs -> commands.
  - Note: not assigned to a specific 9C–9G sub-phase; included for utility RTUs.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register


@register("dnp3")
class Dnp3Driver(BaseDriver):
    domain = "microgrid"

    def connect(self) -> None:
        raise NotImplementedError("DNP3 master not yet implemented")

    def read_telemetry(self) -> dict:
        raise NotImplementedError

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        return CommandResult("FAILED", f"unsupported command '{command_type}'")
