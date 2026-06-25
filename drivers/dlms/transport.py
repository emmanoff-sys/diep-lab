"""DLMS TCP transport: length-prefixed framing plumbing.

Threaded TCP server for the simulator + connect/recv helpers for the client.
DLMS PDUs (encoded by :mod:`dlms.protocol`) are carried one-per-frame.

HDLC interface support (SNRM/UA framing) is added in Phase 2.
"""
from __future__ import annotations

import logging
import socket
import threading

from . import protocol

logger = logging.getLogger("diep-driver.dlms.transport")


class DlmsTcpServer:
    """Threaded TCP server. ``handler`` maps a received PDU (bytes) to a reply
    PDU (bytes) or ``None`` (no reply). ``port=0`` binds an ephemeral port that
    is resolved and returned by :meth:`start` (for tests)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, handler=None):
        self.host = host
        self.port = port
        self.handler = handler
        self._sock = None
        self._running = False

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._running = True
        threading.Thread(target=self._serve, name="dlms-sim", daemon=True).start()
        return self.port

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def _serve(self) -> None:
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5.0)
            buf = b""
            try:
                while self._running:
                    data = conn.recv(2048)
                    if not data:
                        break
                    buf += data
                    pdus, used = protocol.unframe(buf)
                    if used:
                        buf = buf[used:]
                    for pdu in pdus:
                        reply = self.handler(pdu) if self.handler else None
                        if reply is not None:
                            conn.sendall(protocol.frame(reply))
            except (socket.timeout, OSError):
                pass


def recv_pdus(sock: socket.socket, timeout: float = 5.0):
    """Read until at least one complete framed PDU arrives (or timeout)."""
    sock.settimeout(timeout)
    buf = b""
    try:
        while True:
            data = sock.recv(2048)
            if not data:
                break
            buf += data
            pdus, _ = protocol.unframe(buf)
            if pdus:
                return pdus
    except socket.timeout:
        pass
    pdus, _ = protocol.unframe(buf)
    return pdus


# ---------------------------------------------------------------------------
# HDLC framing (IEC 62056-46 / ISO/IEC 13239) — minimal subset (Phase 2)
# ---------------------------------------------------------------------------
# Parallel to the wrapper/TCP framing above; selected in DlmsMeterClient via
# interface="hdlc".
# ⚠️ See drivers/dlms/protocol.py VALIDATION CAVEAT: this is a MINIMAL HDLC
# subset (1-byte address field; SNRM/UA U-frames; AARQ/AARE/GET carried in
# I-frames; no parameter negotiation in SNRM/UA info fields) and is NOT yet
# validated against a real meter's HDLC link layer.

HDLC_FLAG = 0x7E
# U-frame control bytes (DLMS HDLC, P/F bit set).
HDLC_SNRM = 0x93            # Set Normal Response Mode
HDLC_UA = 0x73              # Unnumbered Acknowledgement
HDLC_DISC = 0x53            # Disconnect


def _fcs16(data: bytes) -> int:
    """HDLC FCS — CRC-16/CCITT (reflected poly 0x8408, init 0xFFFF, final XOR)."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc ^ 0xFFFF


def build_hdlc_frame(address: int, control: int, info: bytes = b"") -> bytes:
    """Build: FLAG | addr(1B) | control | info | FCS(2B, LE) | FLAG.

    1-byte address field = (address << 1) | extension-bit. In DLMS HDLC the
    address field carries the SERVER (meter) HDLC address in both directions.
    """
    body = bytes([(address << 1) | 0x01, control & 0xFF]) + bytes(info)
    fcs = _fcs16(body)
    return (bytes([HDLC_FLAG]) + body
            + bytes([fcs & 0xFF, (fcs >> 8) & 0xFF])
            + bytes([HDLC_FLAG]))


def parse_hdlc_frame(frame: bytes):
    """Parse an HDLC frame -> (address, control, info). Raises on bad flags/FCS."""
    if len(frame) < 5 or frame[0] != HDLC_FLAG or frame[-1] != HDLC_FLAG:
        raise ValueError("not an HDLC frame (bad flag delimiters)")
    body = frame[1:-3]                       # drop open flag, FCS(2), close flag
    fcs = frame[-3] | (frame[-2] << 8)
    if _fcs16(body) != fcs:
        raise ValueError("HDLC FCS mismatch")
    if len(body) < 2:
        raise ValueError("HDLC frame body too short")
    return body[0] >> 1, body[1], body[2:]


def build_snrm(server_address: int, info: bytes = b"") -> bytes:
    return build_hdlc_frame(server_address, HDLC_SNRM, info)


def build_ua(server_address: int, info: bytes = b"") -> bytes:
    return build_hdlc_frame(server_address, HDLC_UA, info)


def is_u_frame(control: int) -> bool:
    return (control & 0x03) == 0x03


def is_i_frame(control: int) -> bool:
    return (control & 0x01) == 0x00


def build_iframe(server_address: int, send_seq: int, recv_seq: int, info: bytes) -> bytes:
    """I-frame: control = N(R)<<5 | N(S)<<1 | 0 (I-frame marker). P/F bit = 0."""
    control = ((recv_seq & 0x07) << 5) | ((send_seq & 0x07) << 1)
    return build_hdlc_frame(server_address, control, info)


def iframe_seq(control: int):
    """Return (send_seq N(S), recv_seq N(R)) for an I-frame control byte."""
    return (control >> 1) & 0x07, (control >> 5) & 0x07


def recv_hdlc_frame(sock: socket.socket, timeout: float = 5.0) -> bytes:
    """Read one flag-delimited HDLC frame from the socket (until the close flag)."""
    sock.settimeout(timeout)
    buf = bytearray()
    started = False
    try:
        while True:
            b = sock.recv(1)
            if not b:
                break
            byte = b[0]
            if byte == HDLC_FLAG:
                if started and len(buf) > 2:        # closing flag
                    return bytes([HDLC_FLAG]) + bytes(buf) + bytes([HDLC_FLAG])
                buf = bytearray()                   # opening / inter-frame flag
                started = True
                continue
            if started:
                buf.append(byte)
    except socket.timeout:
        pass
    if started and len(buf) > 2:
        return bytes([HDLC_FLAG]) + bytes(buf) + bytes([HDLC_FLAG])
    raise IOError("no complete HDLC frame received")
