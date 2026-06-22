"""DNP3 outstation adapter — microgrid/RTU vertical.

Bridges a DNP3 outstation into the DIEP MQTT bus using the same SDK + Runner as
the other drivers, so it is a drop-in for the existing ingestor/twin/DERMS path
(publishes diep/microgrid/<id>, handles .../cmd -> .../ack).

The DNP3 link is pluggable (P3-3): an in-process MockDnp3Outstation by default
(no dependency), or a real DNP3/TCP master (`pydnp3`/opendnp3) when the device's
config selects `transport: "tcp"` against real hardware. The driver code below is
transport-agnostic — see transport.py. Pointing a device at field hardware is a
config edit, not a code change.

Point map: see models.py. Commands: island / grid_connect (breaker CROB) and
set_setpoint (analog output) — the microgrid command vocabulary.

Config keys: host (default "mock"), port (DNP3/TCP, default 20000),
transport ("mock" | "tcp"; inferred from host when omitted),
master_addr / outstation_addr / scan_seconds (real transport only).
"""
from __future__ import annotations

import logging

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .transport import make_transport

logger = logging.getLogger("diep-driver.dnp3")


@register("dnp3")
class Dnp3Driver(BaseDriver):
    domain = "microgrid"

    def __init__(self, device_id: str, config: dict | None = None):
        super().__init__(device_id, config)
        self.host = self.config.get("host", "mock")
        self.port = int(self.config.get("port", 20000))  # DNP3/TCP default 20000
        self.station = None

    # --- protocol session -------------------------------------------------
    def connect(self) -> None:
        """Open the DNP3 link via the configured transport (mock or real master)."""
        if self.station is None:
            self.station = make_transport(self.host, self.port, self.config)
        self.station.connect()
        logger.info("%s DNP3 link up via %s transport (%s:%s)",
                    self.device_id, type(self.station).__name__, self.host, self.port)

    def disconnect(self) -> None:
        if self.station is not None:
            self.station.close()

    # --- telemetry --------------------------------------------------------
    def read_telemetry(self) -> dict:
        s = self.station
        return {
            "voltage": s.read_analog(models.AI_VOLTAGE),
            "frequency": s.read_analog(models.AI_FREQUENCY),
            "pcc_kw": s.read_analog(models.AI_PCC_KW),
            "load_kw": s.read_analog(models.AI_LOAD_KW),
            "solar_kw": s.read_analog(models.AI_SOLAR_KW),
            "grid_connected": bool(s.read_binary(models.BI_GRID_CONNECTED)),
            # P3-2: echo the accepted PCC setpoint so a governed set_setpoint can be
            # verified against what the outstation actually latched (AO_SETPOINT_KW).
            "setpoint_kw": float(s.read_setpoint()),
        }

    def normalize(self, native: dict) -> dict:
        # Map PCC active power to canonical power_kw and split into grid import/export.
        pcc = float(native.get("pcc_kw", 0.0))
        return {
            "voltage": native.get("voltage", 0.0),
            "frequency": native.get("frequency", 0.0),
            "power_kw": pcc,
            "solar_kw": native.get("solar_kw", 0.0),
            "grid_import_kw": max(0.0, pcc),
            "grid_export_kw": max(0.0, -pcc),
            # microgrid extras carried in the MQTT payload
            "load_kw": native.get("load_kw", 0.0),
            "grid_connected": native.get("grid_connected", True),
            "mode": "grid_connected" if native.get("grid_connected", True) else "islanded",
            "setpoint_kw": native.get("setpoint_kw", 0.0),
        }

    # --- commands ---------------------------------------------------------
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")
        if command_type == "island":
            ok = self.station.operate_binary(models.BO_BREAKER, 0)      # trip
            return CommandResult("ACKED" if ok else "FAILED",
                                 None if ok else "breaker trip not confirmed by outstation")
        if command_type == "grid_connect":
            ok = self.station.operate_binary(models.BO_BREAKER, 1)      # close
            return CommandResult("ACKED" if ok else "FAILED",
                                 None if ok else "breaker close not confirmed by outstation")
        if command_type == "set_setpoint":
            sp = params.get("setpoint_kw")
            if sp is None:
                return CommandResult("FAILED", "set_setpoint requires setpoint_kw")
            ok = self.station.operate_analog(models.AO_SETPOINT_KW, float(sp))
            return CommandResult("ACKED" if ok else "FAILED",
                                 None if ok else "setpoint not confirmed by outstation")
        return CommandResult("FAILED", f"unhandled command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return {"island", "grid_connect", "set_setpoint"}
