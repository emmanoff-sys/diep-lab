"""DlmsMeterClient — minimal DLMS/COSEM client over TCP (wrapper) or HDLC.

Establishes an ACSE association (AARQ/AARE) then reads COSEM "Data" objects by
OBIS logical name (attribute 2 = value). Two parallel transports, selected by
``interface``:
  - "tcp"  : wrapper/TCP framing (Phase 1) — AARQ/AARE/GET carried one-per-frame.
  - "hdlc" : HDLC link layer (Phase 2) — SNRM/UA handshake, then AARQ/AARE/GET
             carried inside HDLC I-frames.

⚠️ See dlms/protocol.py VALIDATION CAVEAT: minimal DLMS/COSEM + HDLC subset,
not yet meter-validated. The HDLC framing/SNRM-UA/I-frame logic is unit-tested
in isolation (tests/test_dlms_hdlc.py); a client↔simulator HDLC round-trip is
future validation.
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
        if interface not in ("tcp", "hdlc"):
            raise ValueError(f"unsupported interface {interface!r} (use 'tcp' or 'hdlc')")
        self.interface = interface
        self._sock: socket.socket | None = None
        self._invoke = 0
        self._ns = 0          # HDLC I-frame send-sequence N(S)

    # -- association ------------------------------------------------------
    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        if self.interface == "hdlc":
            self._hdlc_link_setup()
            self._hdlc_aarq()
        else:
            self._tcp_send(protocol.build_aarq(self.client_address, self.server_address))
            self._tcp_expect_aare()
        logger.info("DLMS association established with %s:%s (%s)",
                    self.host, self.port, self.interface)

    def _tcp_expect_aare(self) -> None:
        pdus = transport.recv_pdus(self._sock, self.timeout)
        if not pdus:
            raise ConnectionError("no AARE received during association")
        result, _ver = protocol.parse_aare(pdus[0])
        if result != protocol.ACCEPTED:
            raise ConnectionError(f"DLMS association rejected (result={result})")

    def _hdlc_link_setup(self) -> None:
        """SNRM (client→server, U-frame); expect UA back."""
        self._sock.sendall(transport.build_snrm(self.server_address))
        ua = transport.recv_hdlc_frame(self._sock, self.timeout)
        _addr, ctrl, _info = transport.parse_hdlc_frame(ua)
        if ctrl != transport.HDLC_UA:
            raise ConnectionError(f"expected UA after SNRM, got control {ctrl:#04x}")

    def _hdlc_aarq(self) -> None:
        """AARQ carried in an HDLC I-frame; expect AARE back in an I-frame."""
        aarq = protocol.build_aarq(self.client_address, self.server_address)
        self._sock.sendall(transport.build_iframe(self.server_address, self._ns, 0, aarq))
        frame = transport.recv_hdlc_frame(self._sock, self.timeout)
        _addr, ctrl, info = transport.parse_hdlc_frame(frame)
        if not transport.is_i_frame(ctrl):
            raise ConnectionError("AARE not received in an I-frame")
        result, _ver = protocol.parse_aare(info)
        if result != protocol.ACCEPTED:
            raise ConnectionError(f"DLMS association rejected (result={result})")
        self._ns = (self._ns + 1) & 0x07

    # -- read -------------------------------------------------------------
    def read_meter(self, obis: str):
        """Read the value attribute (2) of COSEM Data object ``obis``."""
        if self._sock is None:
            raise ConnectionError("not associated")
        self._invoke = (self._invoke + 1) & 0xFF
        req = protocol.build_get_request(
            self._invoke, protocol.DATA_CLASS_ID,
            protocol.obis_to_bytes(obis), protocol.VALUE_ATTRIBUTE)
        if self.interface == "hdlc":
            self._sock.sendall(transport.build_iframe(self.server_address, self._ns, 0, req))
            frame = transport.recv_hdlc_frame(self._sock, self.timeout)
            _addr, ctrl, info = transport.parse_hdlc_frame(frame)
            if not transport.is_i_frame(ctrl):
                raise IOError("GET response not received in an I-frame")
            pdu = info
            self._ns = (self._ns + 1) & 0x07
        else:
            self._tcp_send(req)
            pdus = transport.recv_pdus(self._sock, self.timeout)
            if not pdus:
                raise IOError("no GET response")
            pdu = pdus[0]
        _iid, result, value_bytes = protocol.parse_get_response(pdu)
        if result != protocol.ACCEPTED:
            raise IOError(f"GET for {obis} failed (result={result})")
        return protocol.decode_value(value_bytes)

    # -- teardown ---------------------------------------------------------
    def disconnect(self) -> None:
        if self._sock is None:
            return
        try:
            if self.interface == "hdlc":
                self._sock.sendall(transport.build_hdlc_frame(self.server_address, transport.HDLC_DISC))
            else:
                self._tcp_send(protocol.build_release_request())
                transport.recv_pdus(self._sock, 1.0)
        except OSError:
            pass
        finally:
            self._sock.close()
            self._sock = None

    def _tcp_send(self, pdu: bytes) -> None:
        self._sock.sendall(protocol.frame(pdu))

    # context-manager convenience
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()
