"""Modbus TCP transport for the SunSpec driver and its simulator.

Two ways to talk Modbus:
  - `open_modbus()` returns a client. If `pymodbus` is importable (the production
    edge build), it wraps it; otherwise it uses the built-in pure-socket client
    below so the driver runs in any environment (host, CI) with no extra deps.
  - `ModbusTcpServer` is a minimal pure-socket server used by the simulator.

The built-in client/server implement just the SunSpec working set: FC3 (read
holding registers) and FC16 (write multiple registers), with request auto-chunking
to respect the 125-register Modbus limit. Modbus addresses are passed through
verbatim (the driver and simulator agree on the SunSpec base), so there is no
1-based/0-based ambiguity between the two sides.
"""
from __future__ import annotations

import socket
import struct
import logging
import threading

logger = logging.getLogger("diep-driver.sunspec.modbus")

_MAX_READ = 125   # Modbus FC3 max registers per request
_MAX_WRITE = 123  # Modbus FC16 max registers per request


# --- built-in pure-socket client -------------------------------------------
class _BuiltinModbusClient:
    def __init__(self, host: str, port: int = 502, unit: int = 1, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self._tx = 0

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None

    def _next_tx(self) -> int:
        self._tx = (self._tx + 1) & 0xFFFF
        return self._tx

    def _txn(self, pdu: bytes) -> bytes:
        if self.sock is None:
            raise ConnectionError("Modbus client not connected")
        tx = self._next_tx()
        # MBAP: transaction id, protocol id (0), length, unit id.
        frame = struct.pack(">HHHB", tx, 0, len(pdu) + 1, self.unit) + pdu
        self.sock.sendall(frame)
        header = self._recv_exact(7)
        rx_tx, proto, length, _unit = struct.unpack(">HHHB", header)
        body = self._recv_exact(length - 1)
        if rx_tx != tx:
            raise IOError(f"Modbus transaction id mismatch (sent {tx}, got {rx_tx})")
        if body and body[0] & 0x80:  # exception response
            code = body[1] if len(body) > 1 else 0
            raise IOError(f"Modbus exception function=0x{body[0]:02x} code={code}")
        return body

    def _recv_exact(self, n: int) -> bytes:
        chunks = []
        remaining = n
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError("Modbus socket closed mid-frame")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read_holding(self, addr: int, count: int) -> list[int]:
        out: list[int] = []
        start = addr
        remaining = count
        while remaining > 0:
            n = min(remaining, _MAX_READ)
            pdu = struct.pack(">BHH", 0x03, start, n)
            body = self._txn(pdu)
            byte_count = body[1]
            regs = struct.unpack(f">{byte_count // 2}H", body[2:2 + byte_count])
            out.extend(regs)
            start += n
            remaining -= n
        return out

    def write_registers(self, addr: int, values: list[int]) -> None:
        start = addr
        idx = 0
        while idx < len(values):
            chunk = values[idx:idx + _MAX_WRITE]
            n = len(chunk)
            data = struct.pack(f">{n}H", *(v & 0xFFFF for v in chunk))
            pdu = struct.pack(">BHHB", 0x10, start, n, n * 2) + data
            self._txn(pdu)
            start += n
            idx += n


# --- pymodbus adapter ------------------------------------------------------
class _PymodbusClient:
    """Adapter exposing the same surface over pymodbus (production edge build)."""

    def __init__(self, host: str, port: int = 502, unit: int = 1, timeout: float = 5.0):
        from pymodbus.client import ModbusTcpClient  # imported lazily
        self.unit = unit
        self._c = ModbusTcpClient(host=host, port=port, timeout=timeout)

    def connect(self) -> None:
        if not self._c.connect():
            raise ConnectionError("pymodbus failed to connect")

    def close(self) -> None:
        self._c.close()

    def read_holding(self, addr: int, count: int) -> list[int]:
        out: list[int] = []
        start = addr
        remaining = count
        while remaining > 0:
            n = min(remaining, _MAX_READ)
            rr = self._c.read_holding_registers(start, count=n, slave=self.unit)
            if rr.isError():
                raise IOError(f"pymodbus read error at {start}: {rr}")
            out.extend(rr.registers)
            start += n
            remaining -= n
        return out

    def write_registers(self, addr: int, values: list[int]) -> None:
        rq = self._c.write_registers(addr, [v & 0xFFFF for v in values], slave=self.unit)
        if rq.isError():
            raise IOError(f"pymodbus write error at {addr}: {rq}")


def open_modbus(host: str, port: int = 502, unit: int = 1, timeout: float = 5.0):
    """Return a connected Modbus client, preferring pymodbus when available."""
    try:
        import pymodbus  # noqa: F401
        client = _PymodbusClient(host, port, unit, timeout)
        logger.debug("using pymodbus transport")
    except ImportError:
        client = _BuiltinModbusClient(host, port, unit, timeout)
        logger.debug("pymodbus not available; using built-in Modbus client")
    client.connect()
    return client


# --- minimal pure-socket server (for the simulator) ------------------------
class ModbusTcpServer:
    """Threaded Modbus TCP server backed by an in-memory register dict.

    The simulator seeds `registers` and may pass `on_read`/`on_write` hooks:
      - on_read(server): called before serving a read (refresh dynamic registers);
      - on_write(addr, values): called after a write (react to control commands).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 1502,
                 on_read=None, on_write=None):
        self.host = host
        self.port = port
        self.registers: dict[int, int] = {}
        self.on_read = on_read
        self.on_write = on_write
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    def set_registers(self, base: int, values: list[int]) -> None:
        with self._lock:
            for i, v in enumerate(values):
                self.registers[base + i] = v & 0xFFFF

    def start(self) -> int:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]  # resolve port 0 -> actual
        self._running = True
        self._thread = threading.Thread(target=self._serve, name="modbus-sim", daemon=True)
        self._thread.start()
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

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            while self._running:
                try:
                    header = self._recv_exact(conn, 7)
                except (ConnectionError, OSError):
                    return
                if header is None:
                    return
                tx, proto, length, unit = struct.unpack(">HHHB", header)
                try:
                    pdu = self._recv_exact(conn, length - 1)
                except (ConnectionError, OSError):
                    return
                if pdu is None:
                    return
                resp_pdu = self._dispatch(pdu)
                frame = struct.pack(">HHHB", tx, 0, len(resp_pdu) + 1, unit) + resp_pdu
                try:
                    conn.sendall(frame)
                except OSError:
                    return

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int):
        chunks = []
        remaining = n
        while remaining:
            chunk = conn.recv(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _dispatch(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        if fc == 0x03:  # read holding registers
            start, qty = struct.unpack(">HH", pdu[1:5])
            if self.on_read:
                self.on_read(self)
            with self._lock:
                regs = [self.registers.get(start + i, 0) for i in range(qty)]
            data = struct.pack(f">{qty}H", *regs)
            return struct.pack(">BB", 0x03, qty * 2) + data
        if fc == 0x10:  # write multiple registers
            start, qty = struct.unpack(">HH", pdu[1:5])
            values = list(struct.unpack(f">{qty}H", pdu[6:6 + qty * 2]))
            with self._lock:
                for i, v in enumerate(values):
                    self.registers[start + i] = v & 0xFFFF
            if self.on_write:
                self.on_write(start, values)
            return struct.pack(">BHH", 0x10, start, qty)
        # Unsupported function -> Modbus exception (illegal function).
        return struct.pack(">BB", fc | 0x80, 0x01)
