"""OCPP EV-charger adapter (Phase 9F) — ARCHITECTURAL EXCEPTION.

Unlike the polling drivers, OCPP chargers are CLIENTS that dial INTO a Central
System (CSMS) over WebSocket. So this is not a poll loop driven by Runner — it is
a small CSMS service. This stub documents that shape; the real implementation is
a separate service (Wave 3), not a BaseDriver poller.

Implementation TODO:
  - Run a WebSocket CSMS (lib: `ocpp` by mobilityhouse) for OCPP 1.6 + 2.0.1.
  - Inbound BootNotification/StatusNotification/MeterValues -> publish telemetry
    to diep/charger/<id> (power_kw, session energy, connector status).
  - DIEP commands (start/stop/set limit) -> OCPP RemoteStartTransaction /
    RemoteStopTransaction / SetChargingProfile; map call results to acks.
Vendors: ABB, Schneider, ChargePoint, Delta, Autel.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register


@register("ocpp")
class OcppChargerDriver(BaseDriver):
    domain = "charger"

    def connect(self) -> None:
        raise NotImplementedError(
            "OCPP is a CSMS server role — implement as a WebSocket service, not a poller (Wave 3)"
        )

    def read_telemetry(self) -> dict:
        # Telemetry is pushed by the charger via MeterValues, not polled.
        raise NotImplementedError

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")
        raise NotImplementedError

    def supported_commands(self) -> set[str]:
        return {"start_charging", "stop_charging", "set_limit"}
