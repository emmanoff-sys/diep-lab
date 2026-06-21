"""DNP3 outstation adapter — microgrid/RTU vertical (mock implementation).

Bridges a DNP3 outstation into the DIEP MQTT bus using the same SDK + Runner as
the other drivers, so it is a drop-in for the existing ingestor/twin/DERMS path
(publishes diep/microgrid/<id>, handles .../cmd -> .../ack). The DNP3 link is a
MockDnp3Outstation (no opendnp3/pydnp3 dependency) — swap connect() for a real
DNP3 master to talk to field hardware; everything else is unchanged.

Point map: see models.py. Commands: island / grid_connect (breaker CROB) and
set_setpoint (analog output) — the microgrid command vocabulary.

Config keys: host (default "mock"), port (informational for the mock).
"""
from __future__ import annotations

import logging

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .sim import MockDnp3Outstation

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
        # Mock: an in-process outstation. A real driver would open a DNP3 master
        # link here (e.g. opendnp3) to host:port and run integrity polls.
        if self.station is None:
            self.station = MockDnp3Outstation()
        logger.info("%s DNP3 master attached to outstation %s:%s (mock)",
                    self.device_id, self.host, self.port)

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
        }

    # --- commands ---------------------------------------------------------
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")
        if command_type == "island":
            self.station.operate_binary(models.BO_BREAKER, 0)      # trip
            return CommandResult("ACKED", None)
        if command_type == "grid_connect":
            self.station.operate_binary(models.BO_BREAKER, 1)      # close
            return CommandResult("ACKED", None)
        if command_type == "set_setpoint":
            sp = params.get("setpoint_kw")
            if sp is None:
                return CommandResult("FAILED", "set_setpoint requires setpoint_kw")
            self.station.operate_analog(models.AO_SETPOINT_KW, float(sp))
            return CommandResult("ACKED", None)
        return CommandResult("FAILED", f"unhandled command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return {"island", "grid_connect", "set_setpoint"}
