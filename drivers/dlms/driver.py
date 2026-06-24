"""DLMS/COSEM smart-meter adapter (Phase 9C / ami-ingest) — BaseDriver wrapper.

This driver is a thin :class:`BaseDriver` adapter over :class:`DlmsMeterClient`,
which performs the DLMS association (AARQ/AARE) and reads COSEM "Data" objects by
OBIS logical name:
    1.0.32.7.0.255 -> voltage, 1.0.31.7.0.255 -> current,
    1.0.1.7.0.255  -> active power, 1.0.14.7.0.255 -> frequency.

⚠️ See dlms/protocol.py VALIDATION CAVEAT: minimal DLMS subset, not yet
meter-validated. DLMS meters are read-only in this profile.
"""
from __future__ import annotations

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .client import DlmsMeterClient


@register("dlms")
class DlmsMeterDriver(BaseDriver):
    domain = "meter"
    aliases = {
        "obis_voltage": "voltage",
        "obis_current": "current",
        "obis_active_power_kw": "power_kw",
        "obis_frequency": "frequency",
    }

    def __init__(self, device_id: str, config: dict | None = None):
        super().__init__(device_id, config)
        cfg = self.config or {}
        self._client = DlmsMeterClient(
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 4060)),
            interface=cfg.get("interface", "tcp"),
            timeout=float(cfg.get("timeout", 5.0)),
            client_address=int(cfg.get("client_address", 16)),
            server_address=int(cfg.get("server_address", 1)),
        )

    def connect(self) -> None:
        self._client.connect()

    def read_telemetry(self) -> dict:
        return {field: self._client.read_meter(ln) for field, ln in models.OBIS.items()}

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        return CommandResult("FAILED", "DLMS meters are read-only in this profile")

    def disconnect(self) -> None:
        self._client.disconnect()
