"""Minimal DLMS/COSEM PDU codec for the Phase-1 client + simulator.

⚠️ VALIDATION CAVEAT — read before relying on this:
This is a MINIMAL, self-consistent DLMS/COSEM wire profile implemented from
spec recollection for Phase-1 testing WITHOUT live meters or a reference
server. The PDU *tags* and the protocol *structure* (ACSE AARQ/AARE
association; xDLMS GetRequest/GetResponse; logical-name referencing; OBIS
logical names; attribute 2 = value) follow DLMS/COSEM (IEC 62056). The body
*encoding*, however, is a documented minimal subset — NOT full BER for ACSE
and NOT full A-XDR for data. It has NOT been validated against a real DLMS
meter or a known-good stack. Validate (and harden the encoding) against target
hardware before any field/production use. See Phase 3+ for real-meter work.

Transport frame (TCP; documented, length-prefixed):
    [VER:u8 = 1][LEN:u16 BE][PDU]
PDU leading tag (DLMS/COSEM):
    ACSE : AARQ=0x60  AARE=0x61  RLRQ=0x62 (release request)  RLRE=0x63
    xDLMS: GET_REQUEST_NORMAL=0xC0  GET_RESPONSE_NORMAL=0xC4
OBIS logical name: 6 octets (A.B.C.D.E.F). Value attribute ordinal = 2.
COSEM "Data" interface class id = 1.
"""
from __future__ import annotations

import struct

# --- PDU tags (DLMS/COSEM) -------------------------------------------------
AARQ = 0x60                # ACSE association request
AARE = 0x61                # ACSE association response
RLRQ = 0x62                # release request
RLRE = 0x63                # release response
GET_REQUEST_NORMAL = 0xC0
GET_RESPONSE_NORMAL = 0xC4

# Association / Get result codes.
ACCEPTED = 0
REJECTED = 1
OBJECT_UNDEFINED = 2          # GET target OBIS not served by this meter

# COSEM constants.
DATA_CLASS_ID = 1          # "Data" interface class
VALUE_ATTRIBUTE = 2        # attribute 2 == value
FRAME_VER = 1

# Minimal A-XDR-ish data type tags used for scalar readings.
TYPE_UINT32 = 0x06
TYPE_FLOAT64 = 0x0F


# --- OBIS logical name <-> 6 octets ---------------------------------------
def obis_to_bytes(obis: str) -> bytes:
    parts = [int(x) for x in obis.split(".")]
    if len(parts) != 6 or not all(0 <= p <= 255 for p in parts):
        raise ValueError(f"OBIS must be 6 octets A.B.C.D.E.F (each 0..255): {obis!r}")
    return bytes(parts)


def bytes_to_obis(b: bytes) -> str:
    if len(b) < 6:
        raise ValueError("OBIS needs 6 octets")
    return ".".join(str(x) for x in b[:6])


# --- minimal data codec ----------------------------------------------------
def encode_value(v) -> bytes:
    """Encode a scalar meter reading (int -> uint32, else float64)."""
    if isinstance(v, bool):
        raise TypeError("bool is not a DLMS scalar here")
    if isinstance(v, int):
        return bytes([TYPE_UINT32]) + struct.pack(">I", v & 0xFFFFFFFF)
    return bytes([TYPE_FLOAT64]) + struct.pack(">d", float(v))


def decode_value(buf: bytes):
    t = buf[0]
    rest = buf[1:]
    if t == TYPE_UINT32:
        return struct.unpack(">I", rest[:4])[0]
    if t == TYPE_FLOAT64:
        return struct.unpack(">d", rest[:8])[0]
    raise ValueError(f"unsupported DLMS data type tag {t:#04x}")


# --- transport framing -----------------------------------------------------
def frame(pdu: bytes) -> bytes:
    if len(pdu) > 0xFFFF:
        raise ValueError("PDU exceeds 16-bit length")
    return bytes([FRAME_VER]) + struct.pack(">H", len(pdu)) + pdu


def unframe(buf: bytes):
    """Split buf into complete PDUs. Returns (pdus, bytes_consumed)."""
    out, i = [], 0
    while i + 3 <= len(buf):
        if buf[i] != FRAME_VER:
            raise ValueError(f"bad frame version {buf[i]:#04x}")
        ln = struct.unpack(">H", buf[i + 1:i + 3])[0]
        if i + 3 + ln > len(buf):
            break
        out.append(buf[i + 3:i + 3 + ln])
        i += 3 + ln
    return out, i


# --- ACSE association PDUs (minimal subset) --------------------------------
def build_aarq(client_address: int = 16, server_address: int = 1,
               dlms_version: int = 6) -> bytes:
    return bytes([AARQ, client_address & 0xFF, server_address & 0xFF, dlms_version])


def parse_aarq(pdu: bytes) -> dict:
    if len(pdu) < 4 or pdu[0] != AARQ:
        raise ValueError("not an AARQ")
    return {"client_address": pdu[1], "server_address": pdu[2], "dlms_version": pdu[3]}


def build_aare(dlms_version: int = 6, result: int = ACCEPTED) -> bytes:
    return bytes([AARE, result, dlms_version])


def parse_aare(pdu: bytes):
    if len(pdu) < 3 or pdu[0] != AARE:
        raise ValueError("not an AARE")
    return pdu[1], pdu[2]          # (result, dlms_version)


def build_release_request() -> bytes:
    return bytes([RLRQ])


def build_release_response() -> bytes:
    return bytes([RLRE])


# --- xDLMS GetRequest / GetResponse (minimal subset) -----------------------
def build_get_request(invoke_id: int, class_id: int, obis: bytes,
                      attribute: int = VALUE_ATTRIBUTE, access: int = 0) -> bytes:
    if len(obis) != 6:
        raise ValueError("OBIS must be exactly 6 octets")
    return (bytes([GET_REQUEST_NORMAL, invoke_id & 0xFF])
            + struct.pack(">H", class_id & 0xFFFF)
            + bytes(obis)
            + bytes([attribute & 0xFF, access & 0xFF]))


def parse_get_request(pdu: bytes):
    if len(pdu) < 12 or pdu[0] != GET_REQUEST_NORMAL:
        raise ValueError("not a GetRequest-Normal")
    invoke_id = pdu[1]
    class_id = struct.unpack(">H", pdu[2:4])[0]
    obis = pdu[4:10]
    attribute = pdu[10]
    return invoke_id, class_id, obis, attribute


def build_get_response(invoke_id: int, value_bytes: bytes, result: int = ACCEPTED) -> bytes:
    return bytes([GET_RESPONSE_NORMAL, invoke_id & 0xFF, result]) + bytes(value_bytes)


def parse_get_response(pdu: bytes):
    if len(pdu) < 3 or pdu[0] != GET_RESPONSE_NORMAL:
        raise ValueError("not a GetResponse-Normal")
    return pdu[1], pdu[2], pdu[3:]     # (invoke_id, result, value_bytes)
