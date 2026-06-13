"""OCPP 1.6J wire format + canonical telemetry mapping (Phase 9F).

OCPP-J frames are JSON arrays:
  CALL        [2, uniqueId, action, payload]
  CALLRESULT  [3, uniqueId, payload]
  CALLERROR   [4, uniqueId, errorCode, errorDescription, errorDetails]

This module is transport-agnostic (works over any text channel) and dependency
free. It covers the subset DIEP needs: the charge-point-initiated actions
(BootNotification, Heartbeat, StatusNotification, StartTransaction, MeterValues,
StopTransaction) and the CSMS-initiated commands (RemoteStartTransaction,
RemoteStopTransaction, SetChargingProfile), plus the MeterValues -> canonical map.
"""
from __future__ import annotations

import json

CALL = 2
CALLRESULT = 3
CALLERROR = 4


def encode_call(unique_id: str, action: str, payload: dict) -> str:
    return json.dumps([CALL, unique_id, action, payload])


def encode_result(unique_id: str, payload: dict) -> str:
    return json.dumps([CALLRESULT, unique_id, payload])


def encode_error(unique_id: str, code: str, description: str = "") -> str:
    return json.dumps([CALLERROR, unique_id, code, description, {}])


def decode(text: str):
    """Return a tuple describing the frame:
      ("CALL", unique_id, action, payload)
      ("CALLRESULT", unique_id, payload)
      ("CALLERROR", unique_id, code, description)
    """
    msg = json.loads(text)
    mtype = msg[0]
    if mtype == CALL:
        return ("CALL", msg[1], msg[2], msg[3])
    if mtype == CALLRESULT:
        return ("CALLRESULT", msg[1], msg[2])
    if mtype == CALLERROR:
        return ("CALLERROR", msg[1], msg[2], msg[3] if len(msg) > 3 else "")
    raise ValueError(f"unknown OCPP message type {mtype!r}")


# --- canonical mapping -----------------------------------------------------
# OCPP measurand -> handler. Values arrive as strings in sampledValue.
_MEASURAND_KEYS = {
    "Power.Active.Import": "_power_w",
    "Voltage": "voltage",
    "Current.Import": "current",
    "Energy.Active.Import.Register": "_energy_wh",
    "SoC": "vehicle_soc",
}


def meter_values_to_native(meter_value_list: list) -> dict:
    """Flatten an OCPP MeterValues `meterValue` array into a native reading dict.

    Returns canonical-ready keys: voltage, current, power_kw (from W), plus extras
    session_energy_kwh (from Wh) and vehicle_soc.
    """
    native: dict[str, float] = {}
    for mv in meter_value_list:
        for sv in mv.get("sampledValue", []):
            measurand = sv.get("measurand", "Energy.Active.Import.Register")
            key = _MEASURAND_KEYS.get(measurand)
            if key is None:
                continue
            try:
                value = float(sv.get("value"))
            except (TypeError, ValueError):
                continue
            native[key] = value
    out: dict[str, float] = {}
    if "voltage" in native:
        out["voltage"] = native["voltage"]
    if "current" in native:
        out["current"] = native["current"]
    if "_power_w" in native:
        out["power_kw"] = native["_power_w"] / 1000.0
    if "_energy_wh" in native:
        out["session_energy_kwh"] = native["_energy_wh"] / 1000.0
    if "vehicle_soc" in native:
        out["vehicle_soc"] = native["vehicle_soc"]
    return out


def sampled_value(value, measurand: str, unit: str) -> dict:
    """Build one OCPP sampledValue entry (charge-point side)."""
    return {"value": f"{value}", "measurand": measurand, "unit": unit}
