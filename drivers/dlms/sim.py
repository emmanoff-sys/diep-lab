"""DLMS/COSEM smart-meter simulator — serves OBIS objects over TCP.

Mirrors drivers/modbus_meter/sim.py: an in-process TCP server (ephemeral port
for tests) that serves the configured OBIS values, so DlmsMeterClient is
exercised end-to-end with no live meters.

⚠️ See dlms/protocol.py VALIDATION CAVEAT: speaks a minimal DLMS/COSEM subset
(ACSE association + xDLMS GetRequest/GetResponse), not a full/conformant stack.

Standalone (from drivers/):
    python -m dlms.sim --host 127.0.0.1 --port 4060
"""
from __future__ import annotations

import argparse
import logging
import time

from . import models, protocol
from .transport import DlmsTcpServer

logger = logging.getLogger("diep-driver.dlms.sim")


class DlmsMeterSim:
    """A minimal DLMS/COSEM meter serving the OBIS values in ``models.OBIS``."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 voltage=None, current=None, power_kw=None, frequency=None,
                 reject: bool = False):
        values = dict(models.SIM_DEFAULTS)
        for field, val in (("voltage", voltage), ("current", current),
                           ("power_kw", power_kw), ("frequency", frequency)):
            if val is not None:
                values[field] = val
        self.values = values
        self.reject = reject          # reject the association (for error-path tests)
        self._net = DlmsTcpServer(host, port, handler=self._handle)

    def start(self) -> int:
        port = self._net.start()
        logger.info("DLMS meter sim on %s:%d — %s", self._net.host, port, self.values)
        return port

    def stop(self) -> None:
        self._net.stop()

    def _handle(self, pdu: bytes):
        tag = pdu[0]
        if tag == protocol.AARQ:
            result = protocol.REJECTED if self.reject else protocol.ACCEPTED
            return protocol.build_aare(result=result)
        if tag == protocol.RLRQ:
            return protocol.build_release_response()
        if tag == protocol.GET_REQUEST_NORMAL:
            invoke_id, _class_id, obis, _attr = protocol.parse_get_request(pdu)
            field = models.FIELD_BY_OBIS.get(protocol.bytes_to_obis(obis))
            if field is None:
                # OBIS not served by this meter.
                return protocol.build_get_response(invoke_id, b"", protocol.OBJECT_UNDEFINED)
            return protocol.build_get_response(
                invoke_id, protocol.encode_value(self.values[field]))
        logger.warning("sim: unknown PDU tag %#04x", tag)
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DLMS smart-meter simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4060)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    sim = DlmsMeterSim(host=args.host, port=args.port)
    sim.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
