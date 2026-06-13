"""IEC 60870-5-104 ASDU encode/decode + microgrid IOA map + canonical mapping.

An IEC-104 ASDU is:
  [TypeID(1)] [VSQ(1)] [COT(2)] [CommonAddr(2)] [InformationObject...]
where each information object is [IOA(3, little-endian)] [element(s)].

This module covers the subset DIEP's microgrid controller needs:
  monitor  M_ME_NC_1 (13) short-float measurements, M_SP_NA_1 (1) single point
  control  C_SC_NA_1 (45) single command, C_SE_NC_1 (50) short-float setpoint,
           C_IC_NA_1 (100) general interrogation
It is transport-agnostic and dependency-free (shared by driver and RTU simulator).
"""
from __future__ import annotations

import struct

# --- type identifiers ------------------------------------------------------
M_SP_NA_1 = 1     # single-point information
M_ME_NC_1 = 13    # measured value, short floating point
C_SC_NA_1 = 45    # single command
C_SE_NC_1 = 50    # set-point command, short float
C_IC_NA_1 = 100   # general interrogation

# --- causes of transmission ------------------------------------------------
COT_PERIODIC = 1
COT_SPONTANEOUS = 3
COT_ACT = 6        # activation
COT_ACTCON = 7     # activation confirmation
COT_ACTTERM = 10   # activation termination
COT_INTERROGATED = 20  # response to station interrogation
QOI_STATION = 20   # qualifier of interrogation: station (global)

# --- microgrid information object addresses (IOA) --------------------------
IOA_FREQ = 1001        # M_ME_NC_1  Hz
IOA_PCC = 1002         # M_ME_NC_1  kW at point of common coupling (+import/-export)
IOA_SOLAR = 1003       # M_ME_NC_1  kW
IOA_LOAD = 1004        # M_ME_NC_1  kW
IOA_VOLTAGE = 1005     # M_ME_NC_1  V
IOA_SETPOINT = 1006    # M_ME_NC_1  kW (current PCC setpoint, monitor)
IOA_GRID_CONNECTED = 2001  # M_SP_NA_1  1=grid-connected, 0=islanded
IOA_BREAKER = 3001     # C_SC_NA_1  close(1)=grid_connect, open(0)=island
IOA_CMD_SETPOINT = 3002  # C_SE_NC_1  PCC setpoint kW

# Measurement IOA -> native key.
_MEAS_KEYS = {
    IOA_FREQ: "frequency",
    IOA_PCC: "pcc_kw",
    IOA_SOLAR: "solar_kw",
    IOA_LOAD: "load_kw",
    IOA_VOLTAGE: "voltage",
    IOA_SETPOINT: "setpoint_kw",
}


def _ioa_bytes(ioa: int) -> bytes:
    return bytes([ioa & 0xFF, (ioa >> 8) & 0xFF, (ioa >> 16) & 0xFF])


def _read_ioa(b: bytes, off: int) -> int:
    return b[off] | (b[off + 1] << 8) | (b[off + 2] << 16)


def encode_asdu(type_id: int, cot: int, common_addr: int, objects: list) -> bytes:
    """objects: list of (ioa, element_bytes). SQ=0 (each object carries its IOA)."""
    vsq = len(objects) & 0x7F
    out = bytearray([type_id, vsq])
    out += struct.pack("<H", cot & 0xFFFF)       # COT low=cause, high=originator(0)
    out += struct.pack("<H", common_addr & 0xFFFF)
    for ioa, element in objects:
        out += _ioa_bytes(ioa) + element
    return bytes(out)


def decode_asdu(asdu: bytes) -> dict:
    """Decode an ASDU into {type_id, cot, common_addr, objects:[(ioa, value)]}."""
    type_id = asdu[0]
    vsq = asdu[1]
    count = vsq & 0x7F
    sq = bool(vsq & 0x80)
    cot = struct.unpack("<H", asdu[2:4])[0] & 0xFF
    common_addr = struct.unpack("<H", asdu[4:6])[0]
    objects = []
    off = 6
    base_ioa = None
    for i in range(count):
        if sq and i > 0:
            ioa = base_ioa + i
        else:
            ioa = _read_ioa(asdu, off)
            off += 3
            if sq:
                base_ioa = ioa
        value, off = _decode_element(type_id, asdu, off)
        objects.append((ioa, value))
    return {"type_id": type_id, "cot": cot, "common_addr": common_addr, "objects": objects}


def _decode_element(type_id: int, b: bytes, off: int):
    if type_id == M_ME_NC_1:                       # float32 + QDS
        value = struct.unpack("<f", b[off:off + 4])[0]
        return round(value, 4), off + 5
    if type_id == M_SP_NA_1:                        # SIQ (bit0 = state)
        return (b[off] & 0x01), off + 1
    if type_id == C_SC_NA_1:                        # SCO (bit0 = on/off)
        return (b[off] & 0x01), off + 1
    if type_id == C_SE_NC_1:                        # float32 + QOS
        value = struct.unpack("<f", b[off:off + 4])[0]
        return round(value, 4), off + 5
    if type_id == C_IC_NA_1:                        # QOI
        return b[off], off + 1
    raise ValueError(f"unsupported type id {type_id}")


# --- element encoders (for building objects) -------------------------------
def me_nc(value: float) -> bytes:
    return struct.pack("<f", float(value)) + b"\x00"      # value + QDS good


def sp_na(state: int) -> bytes:
    return bytes([state & 0x01])


def sc_na(on: int) -> bytes:
    return bytes([on & 0x01])


def se_nc(value: float) -> bytes:
    return struct.pack("<f", float(value)) + b"\x00"      # value + QOS


def qoi(value: int) -> bytes:
    return bytes([value & 0xFF])


# --- canonical mapping -----------------------------------------------------
def measurements_to_native(decoded_objects: list, type_id: int) -> dict:
    """Pull native keys out of an M_ME_NC_1 / M_SP_NA_1 object list."""
    native: dict = {}
    for ioa, value in decoded_objects:
        if type_id == M_ME_NC_1 and ioa in _MEAS_KEYS:
            native[_MEAS_KEYS[ioa]] = value
        elif type_id == M_SP_NA_1 and ioa == IOA_GRID_CONNECTED:
            native["grid_connected"] = bool(value)
    return native
