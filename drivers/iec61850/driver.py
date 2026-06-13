"""IEC 61850 substation adapter (Phase 9G) — LARGEST / SAFETY-CRITICAL.

STUB. Implementation TODO (Wave 3, isolated test bench required):
  - MMS client (lib: libiec61850 bindings) to read logical nodes / data objects;
    optionally GOOSE for fast status.
  - Requires the device's SCL/ICD file to build the data model.
  - Map MMXU (measurements) -> telemetry; control via XCBR/CSWI with
    select-before-operate (SBO) semantics.
Vendors: Schneider, Siemens, ABB, SEL. Treat as a certified-gateway integration;
do NOT actuate breakers without SBO + interlock validation.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register


@register("iec61850")
class Iec61850Driver(BaseDriver):
    domain = "microgrid"
    aliases = {"MMXU_Hz": "frequency", "MMXU_TotW_kw": "power_kw"}

    def connect(self) -> None:
        raise NotImplementedError("IEC 61850 MMS client not yet implemented (Wave 3)")

    def read_telemetry(self) -> dict:
        raise NotImplementedError

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        # Safety: control points require select-before-operate + interlock checks.
        return CommandResult("FAILED", "61850 control requires SBO validation (not implemented)")

    def supported_commands(self) -> set[str]:
        return {"island", "grid_connect"}
