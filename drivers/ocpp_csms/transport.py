"""Minimal pure-Python WebSocket transport for the OCPP vertical (Phase 9F).

OCPP 1.6J runs over WebSocket: the charge point is the WS **client** that dials
into the CSMS **server**. This module implements just enough of RFC 6455 (text
frames, handshake, client-side masking, ping/pong/close) for both roles, with no
external dependencies — so the CSMS, the charge-point simulator, and the host
selftest all run anywhere. A production CSMS would swap this for `websockets` +
the `ocpp` library; the message layer (models.py) is transport-agnostic.

Path routing: the charge point connects to ws://host:port/<charger_id>, and the
server hands that id to on_connect, mirroring how a real CSMS identifies CPs.
"""
from __future__ import annotations

import os
import socket
import struct
import base64
import hashlib
import logging
import threading

logger = logging.getLogger("diep-driver.ocpp.ws")

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


def _accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + _WS_GUID).encode()).digest()).decode()


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
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


def _encode_frame(payload: str, mask: bool, opcode: int = OP_TEXT) -> bytes:
    data = payload.encode("utf-8")
    header = bytearray([0x80 | opcode])
    length = len(data)
    if length < 126:
        header.append((0x80 if mask else 0) | length)
    elif length < 65536:
        header.append((0x80 if mask else 0) | 126)
        header += struct.pack(">H", length)
    else:
        header.append((0x80 if mask else 0) | 127)
        header += struct.pack(">Q", length)
    if mask:
        key = os.urandom(4)
        header += key
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
    return bytes(header) + data


def _read_frame(sock: socket.socket):
    """Return (opcode, payload_bytes) or None on close/error."""
    hdr = _recv_exact(sock, 2)
    if hdr is None:
        return None
    opcode = hdr[0] & 0x0F
    masked = bool(hdr[1] & 0x80)
    length = hdr[1] & 0x7F
    if length == 126:
        ext = _recv_exact(sock, 2)
        if ext is None:
            return None
        length = struct.unpack(">H", ext)[0]
    elif length == 127:
        ext = _recv_exact(sock, 8)
        if ext is None:
            return None
        length = struct.unpack(">Q", ext)[0]
    mask_key = b""
    if masked:
        mask_key = _recv_exact(sock, 4)
        if mask_key is None:
            return None
    payload = _recv_exact(sock, length) if length else b""
    if payload is None:
        return None
    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return opcode, payload


class WebSocketConnection:
    """A live WS connection (server side). Thread-safe send."""

    def __init__(self, sock: socket.socket, charger_id: str):
        self.sock = sock
        self.charger_id = charger_id
        self._lock = threading.Lock()
        self.open = True

    def send_text(self, text: str) -> None:
        with self._lock:
            if not self.open:
                raise ConnectionError("ws closed")
            self.sock.sendall(_encode_frame(text, mask=False))

    def close(self) -> None:
        self.open = False
        try:
            self.sock.close()
        except OSError:
            pass


class WebSocketServer:
    """Threaded WS server. Calls on_connect(conn) and on_message(conn, text)."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9000,
                 on_connect=None, on_message=None, on_close=None):
        self.host = host
        self.port = port
        self.on_connect = on_connect
        self.on_message = on_message
        self.on_close = on_close
        self._sock: socket.socket | None = None
        self._running = False

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(16)
        self.port = self._sock.getsockname()[1]
        self._running = True
        threading.Thread(target=self._serve, name="ocpp-csms-accept", daemon=True).start()
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
        charger_id = self._handshake(sock)
        if charger_id is None:
            sock.close()
            return
        ws = WebSocketConnection(sock, charger_id)
        if self.on_connect:
            self.on_connect(ws)
        try:
            while self._running and ws.open:
                frame = _read_frame(sock)
                if frame is None:
                    break
                opcode, payload = frame
                if opcode == OP_CLOSE:
                    break
                if opcode == OP_PING:
                    with ws._lock:
                        sock.sendall(_encode_frame(payload.decode("utf-8", "ignore"),
                                                   mask=False, opcode=OP_PONG))
                    continue
                if opcode == OP_TEXT and self.on_message:
                    self.on_message(ws, payload.decode("utf-8"))
        finally:
            ws.open = False
            if self.on_close:
                self.on_close(ws)
            try:
                sock.close()
            except OSError:
                pass

    def _handshake(self, sock: socket.socket) -> str | None:
        # Read the HTTP upgrade request up to the blank line.
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                return None
            data += chunk
            if len(data) > 65536:
                return None
        lines = data.decode("latin1").split("\r\n")
        request_line = lines[0]
        try:
            path = request_line.split(" ")[1]
        except IndexError:
            return None
        charger_id = path.strip("/").split("/")[-1] or "unknown"
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        key = headers.get("sec-websocket-key")
        if not key:
            return None
        subproto = headers.get("sec-websocket-protocol", "")
        resp = [
            "HTTP/1.1 101 Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {_accept_key(key)}",
        ]
        if "ocpp1.6" in subproto:
            resp.append("Sec-WebSocket-Protocol: ocpp1.6")
        resp.append("\r\n")
        sock.sendall("\r\n".join(resp).encode())
        return charger_id


class WebSocketClient:
    """WS client (charge-point side). on_message(text) called per inbound frame."""

    def __init__(self, host: str, port: int, path: str, on_message=None, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.path = "/" + path.lstrip("/")
        self.on_message = on_message
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self._lock = threading.Lock()
        self.open = False

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = [
            f"GET {self.path} HTTP/1.1",
            f"Host: {self.host}:{self.port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            "Sec-WebSocket-Protocol: ocpp1.6",
            "\r\n",
        ]
        self.sock.sendall("\r\n".join(req).encode())
        # Read handshake response.
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("ws handshake failed")
            data += chunk
        if b"101" not in data.split(b"\r\n")[0]:
            raise ConnectionError(f"ws handshake rejected: {data[:80]!r}")
        self.sock.settimeout(None)
        self.open = True
        threading.Thread(target=self._recv_loop, name="ocpp-cp-recv", daemon=True).start()

    def _recv_loop(self) -> None:
        while self.open:
            frame = _read_frame(self.sock)
            if frame is None:
                break
            opcode, payload = frame
            if opcode == OP_CLOSE:
                break
            if opcode == OP_PING:
                with self._lock:
                    self.sock.sendall(_encode_frame(payload.decode("utf-8", "ignore"),
                                                    mask=True, opcode=OP_PONG))
                continue
            if opcode == OP_TEXT and self.on_message:
                self.on_message(payload.decode("utf-8"))
        self.open = False

    def send_text(self, text: str) -> None:
        with self._lock:
            if not self.open:
                raise ConnectionError("ws closed")
            self.sock.sendall(_encode_frame(text, mask=True))

    def close(self) -> None:
        self.open = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
