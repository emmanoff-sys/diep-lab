"""DlmsMeterClient — minimal DLMS/COSEM client (association + OBIS GET) over TCP.

Establishes an ACSE association (AARQ/AARE) then reads COSEM "Data" objects by
OBIS logical name (attribute 2 = value) via xDLMS GetRequest/GetResponse.

⚠️ See dlms/protocol.py VALIDATION CAVEAT: speaks a minimal DLMS/COSEM subset,
not a full/conformant stack, and is NOT yet validated against a real meter.
HDLC interface support is added in Phase 2.
"""
from __future__ import annotations

import logging
import socket

from . import protocol, transport

logger = logging.getLogger("diep-driver.dlms.client")


class DlmsMeterClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 4060,
                 interface: str = "tcp", timeout: float = 5.0,
                 client_address: int = 16, server_address: int = 1):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.client_address = client_address
        self.server_address = server_address
        if interface != "tcp":
            raise NotImplementedError("HDLC interface is added in Phase 2")
        self.interface = interface
        self._sock: socket.socket | None = None
        self._invoke = 0

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        self._send(protocol.build_aarq(self.client_address, self.server_address))
        pdus = transport.recv_pdus(self._sock, self.timeout)
        if not pdus:
            raise ConnectionError("no AARE received during association")
        result, _ver = protocol.parse_aare(pdus[0])
        if result != protocol.ACCEPTED:
            raise ConnectionError(f"DLMS association rejected (result={result})")
        logger.info("DLMS association established with %s:%s", self.host, self.port)

    def read_meter(self, obis: str):
        """Read the value attribute (2) of COSEM Data object ``obis``."""
        if self._sock is None:
            raise ConnectionError("not associated")
        self._invoke = (self._invoke + 1) & 0xFF
        self._send(protocol.build_get_request(
            self._invoke, protocol.DATA_CLASS_ID,
            protocol.obis_to_bytes(obis), protocol.VALUE_ATTRIBUTE))
        pdus = transport.recv_pdus(self._sock, self.timeout)
        if not pdus:
            raise IOError("no GET response")
        _iid, result, value_bytes = protocol.parse_get_response(pdus[0])
        if result != protocol.ACCEPTED:
            raise IOError(f"GET for {obis} failed (result={result})")
        return protocol.decode_value(value_bytes)

    def disconnect(self) -> None:
        if self._sock is None:
            return
        try:
            self._send(protocol.build_release_request())
            transport.recv_pdus(self._sock, 1.0)
        except OSError:
            pass
        finally:
            self._sock.close()
            self._sock = None

    # context-manager convenience
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()

    def _send(self, pdu: bytes) -> None:
        self._sock.sendall(protocol.frame(pdu))
