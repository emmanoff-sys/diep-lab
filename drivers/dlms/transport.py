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
