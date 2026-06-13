"""Microgrid controller adapter over IEC 60870-5-104 (Phase 9G).

Unlike OCPP (9F), IEC-104 is a pollable master/slave SCADA protocol, so this
driver returns to the SDK polling model: it subclasses BaseDriver and is hosted by
the shared Runner exactly like the Modbus drivers (9C/9D/9E). It:

  - connect():        open the IEC-104 connection (TCP + STARTDT) to the RTU;
  - read_telemetry(): issue a General Interrogation, decode M_ME/M_SP responses
                      into canonical telemetry (pcc -> power_kw + grid split,
                      frequency, solar) plus extras (grid_connected, load, mode);
  - execute_command(): island / grid_connect via C_SC (breaker), set_setpoint via
                       C_SE (short-float setpoint command).

domain = "microgrid" matches the dispatcher DOMAIN_MAP and ALLOWED_COMMANDS, so the
controller plugs into the platform with no dispatcher change.

Config keys: host, port (default 2404), common_address (ASDU address, default 1).
"""
from __future__ import annotations

import time
import logging
import threading

from diep_driver import BaseDriver, CommandResult
from diep_driver.registry import register

from . import models
from .transport import Iec104Client

logger = logging.getLogger("diep-driver.microgrid_iec104")


@register("microgrid_iec104")
class MicrogridIec104Driver(BaseDriver):
    domain = "microgrid"
    aliases = {}

    def __init__(self, device_id: str, config: dict | None = None):
        super().__init__(device_id, config)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = int(self.config.get("port", 2404))
        self.ca = int(self.config.get("common_address", 1))
        self.client: Iec104Client | None = None
        self._values: dict[str, float] = {}
        self._grid_connected = True
        self._actcon = threading.Event()
        self._lock = threading.Lock()

    # --- protocol session -------------------------------------------------
    def connect(self) -> None:
        if self.client is None:
            self.client = Iec104Client(self.host, self.port, on_asdu=self._on_asdu,
                                       timeout=float(self.config.get("timeout", 5.0)))
        self.client.connect()
        logger.info("%s connected to IEC-104 %s:%s (CA=%d)",
                    self.device_id, self.host, self.port, self.ca)
        self._interrogate()  # prime the cache

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    # --- inbound ASDU handling -------------------------------------------
    def _on_asdu(self, asdu: bytes) -> None:
        try:
            decoded = models.decode_asdu(asdu)
        except Exception:  # noqa: BLE001 — ignore malformed frames
            return
        tid = decoded["type_id"]
        if tid in (models.M_ME_NC_1, models.M_SP_NA_1):
            native = models.measurements_to_native(decoded["objects"], tid)
            with self._lock:
                for k, v in native.items():
                    if k == "grid_connected":
                        self._grid_connected = v
                    else:
                        self._values[k] = v
        elif decoded["cot"] in (models.COT_ACTCON, models.COT_ACTTERM):
            self._actcon.set()

    def _interrogate(self) -> None:
        asdu = models.encode_asdu(models.C_IC_NA_1, models.COT_ACT, self.ca,
                                  [(0, models.qoi(models.QOI_STATION))])
        self.client.send_asdu(asdu)
        time.sleep(0.4)  # allow the RTU to stream its interrogated dataset

    # --- telemetry --------------------------------------------------------
    def read_telemetry(self) -> dict:
        self._interrogate()
        with self._lock:
            v = dict(self._values)
            grid_connected = self._grid_connected
        return {
            "voltage": v.get("voltage", 0.0),
            "frequency": v.get("frequency", 0.0),
            "solar_kw": v.get("solar_kw", 0.0),
            "pcc_kw": v.get("pcc_kw", 0.0),
            "load_kw": v.get("load_kw", 0.0),
            "setpoint_kw": v.get("setpoint_kw", 0.0),
            "grid_connected": grid_connected,
        }

    def normalize(self, native: dict) -> dict:
        canonical = super().normalize(native)  # voltage, frequency, solar_kw
        pcc = native.get("pcc_kw", 0.0)
        canonical["power_kw"] = pcc
        canonical["grid_import_kw"] = max(0.0, pcc)
        canonical["grid_export_kw"] = max(0.0, -pcc)
        # microgrid-specific extras (carried in the MQTT payload / twin):
        canonical["grid_connected"] = native.get("grid_connected", True)
        canonical["mode"] = "grid_connected" if native.get("grid_connected", True) else "islanded"
        canonical["load_kw"] = native.get("load_kw", 0.0)
        canonical["setpoint_kw"] = native.get("setpoint_kw", 0.0)
        return canonical

    # --- commands ---------------------------------------------------------
    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        if command_type not in self.supported_commands():
            return CommandResult("FAILED", f"unsupported command '{command_type}'")

        if command_type in ("island", "grid_connect"):
            close = 1 if command_type == "grid_connect" else 0  # close=grid-connect
            asdu = models.encode_asdu(models.C_SC_NA_1, models.COT_ACT, self.ca,
                                      [(models.IOA_BREAKER, models.sc_na(close))])
            return self._send_and_confirm(asdu)

        if command_type == "set_setpoint":
            if "setpoint_kw" not in params:
                return CommandResult("FAILED", "set_setpoint requires params.setpoint_kw")
            asdu = models.encode_asdu(models.C_SE_NC_1, models.COT_ACT, self.ca,
                                      [(models.IOA_CMD_SETPOINT,
                                        models.se_nc(float(params["setpoint_kw"])))])
            return self._send_and_confirm(asdu)

        return CommandResult("FAILED", f"unhandled command '{command_type}'")

    def supported_commands(self) -> set[str]:
        return {"island", "grid_connect", "set_setpoint"}

    def _send_and_confirm(self, asdu: bytes, timeout: float = 3.0) -> CommandResult:
        self._actcon.clear()
        try:
            self.client.send_asdu(asdu)
        except Exception as exc:  # noqa: BLE001
            return CommandResult("FAILED", f"send failed: {exc}")
        if not self._actcon.wait(timeout):
            return CommandResult("FAILED", "no activation confirmation from RTU")
        return CommandResult("ACKED", None)
