"""Minimal IEC 60870-5-104 transport over TCP (pure-python, no deps).

IEC-104 wraps ASDUs in an APCI: a 6-byte header (0x68, length, 4 control octets)
carrying I-format (information + send/recv sequence numbers), S-format (supervisory
ack) or U-format (STARTDT/STOPDT/TESTFR) frames. This implements the happy-path
client (controlling station) and server (controlled station / RTU) with STARTDT
handshake and basic sequence tracking — enough to poll measurements (general
interrogation) and issue commands. A production stack adds the full k/w window and
t1/t2/t3 timeout state machine; that is called out in the report's gaps.

Default IEC-104 TCP port is 2404 (overridable for the lab).
"""
from __future__ import annotations

import socket
import struct
import logging
import threading

logger = logging.getLogger("diep-driver.iec104")

START = 0x68
# U-format function codes (control octet 1).
STARTDT_ACT = 0x07
STARTDT_CON = 0x0B
STOPDT_ACT = 0x13
STOPDT_CON = 0x23
TESTFR_ACT = 0x43
TESTFR_CON = 0x83


def _encode_i(asdu: bytes, ns: int, nr: int) -> bytes:
    control = bytes([(ns << 1) & 0xFE, (ns >> 7) & 0xFF,
                     (nr << 1) & 0xFE, (nr >> 7) & 0xFF])
    body = control + asdu
    return bytes([START, len(body)]) + body


def _encode_s(nr: int) -> bytes:
    control = bytes([0x01, 0x00, (nr << 1) & 0xFE, (nr >> 7) & 0xFF])
    return bytes([START, 4]) + control


def _encode_u(func: int) -> bytes:
    return bytes([START, 4, func, 0, 0, 0])


def _recv_exact(sock: socket.socket, n: int):
    chunks = []
    while n:
        try:
            chunk = sock.recv(n)
        except OSError:
            return None
        if not chunk:
            return None
        chunks.append(chunk)
        n -= len(chunk)
    return b"".join(chunks)


def _read_apdu(sock: socket.socket):
    """Return (kind, payload) where kind is 'I'/'S'/'U' or None on close.
    For 'I': payload = (ns, nr, asdu_bytes). For 'U': payload = func. For 'S': nr."""
    hdr = _recv_exact(sock, 2)
    if hdr is None:
        return None
    if hdr[0] != START:
        return None  # desync — bail
    length = hdr[1]
    body = _recv_exact(sock, length)
    if body is None or len(body) < 4:
        return None
    control = body[:4]
    asdu = body[4:]
    if control[0] & 0x01 == 0:               # I-format
        ns = (control[0] | (control[1] << 8)) >> 1
        nr = (control[2] | (control[3] << 8)) >> 1
        return ("I", (ns, nr, asdu))
    if control[0] & 0x03 == 0x01:            # S-format
        nr = (control[2] | (control[3] << 8)) >> 1
        return ("S", nr)
    return ("U", control[0])                 # U-format


class Iec104Peer:
    """Shared I/S/U send logic with sequence tracking for one TCP connection."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.ns = 0   # send sequence number
        self.nr = 0   # receive sequence number
        self._lock = threading.Lock()

    def send_asdu(self, asdu: bytes) -> None:
        with self._lock:
            frame = _encode_i(asdu, self.ns, self.nr)
            self.ns = (self.ns + 1) & 0x7FFF
            self.sock.sendall(frame)

    def send_u(self, func: int) -> None:
        with self._lock:
            self.sock.sendall(_encode_u(func))

    def ack_received(self) -> None:
        """Increment receive counter and S-ack the peer."""
        with self._lock:
            self.nr = (self.nr + 1) & 0x7FFF
            self.sock.sendall(_encode_s(self.nr))


# --- controlled station (RTU server) --------------------------------------
class Iec104Server:
    """Threaded IEC-104 server. on_interrogation(peer) and on_command(peer, asdu)
    are called for received I-frames; the RTU sim wires its measurement/command
    logic to them."""

    def __init__(self, host: str = "0.0.0.0", port: int = 2404,
                 on_asdu=None):
        self.host = host
        self.port = port
        self.on_asdu = on_asdu
        self._sock: socket.socket | None = None
        self._running = False

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._running = True
        threading.Thread(target=self._serve, name="iec104-accept", daemon=True).start()
        return self.port

    def stop(self) -> None:
        self._running = False
        if self._sock:
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

    def _handle(self, sock: socket.socket) -> None:
        peer = Iec104Peer(sock)
        try:
            while self._running:
                apdu = _read_apdu(sock)
                if apdu is None:
                    break
                kind = apdu[0]
                if kind == "U":
                    func = apdu[1]
                    if func == STARTDT_ACT:
                        peer.send_u(STARTDT_CON)
                    elif func == STOPDT_ACT:
                        peer.send_u(STOPDT_CON)
                    elif func == TESTFR_ACT:
                        peer.send_u(TESTFR_CON)
                elif kind == "I":
                    _ns, _nr, asdu = apdu[1]
                    peer.ack_received()
                    if self.on_asdu:
                        self.on_asdu(peer, asdu)
                # S-frames: peer ack of our sends — nothing to do.
        finally:
            try:
                sock.close()
            except OSError:
                pass


# --- controlling station (driver client) ----------------------------------
class Iec104Client:
    """IEC-104 client. on_asdu(asdu_bytes) is called for each inbound I-frame."""

    def __init__(self, host: str, port: int = 2404, on_asdu=None, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.on_asdu = on_asdu
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.peer: Iec104Peer | None = None
        self.open = False
        self._started = threading.Event()

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(None)
        self.peer = Iec104Peer(self.sock)
        self.open = True
        threading.Thread(target=self._recv_loop, name="iec104-recv", daemon=True).start()
        self.peer.send_u(STARTDT_ACT)
        if not self._started.wait(self.timeout):
            raise ConnectionError("IEC-104 STARTDT not confirmed")

    def _recv_loop(self) -> None:
        while self.open:
            apdu = _read_apdu(self.sock)
            if apdu is None:
                break
            kind = apdu[0]
            if kind == "U":
                if apdu[1] == STARTDT_CON:
                    self._started.set()
                elif apdu[1] == TESTFR_ACT:
                    self.peer.send_u(TESTFR_CON)
            elif kind == "I":
                _ns, _nr, asdu = apdu[1]
                self.peer.ack_received()
                if self.on_asdu:
                    self.on_asdu(asdu)
        self.open = False

    def send_asdu(self, asdu: bytes) -> None:
        if not self.open:
            raise ConnectionError("IEC-104 client not connected")
        self.peer.send_asdu(asdu)

    def close(self) -> None:
        self.open = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
