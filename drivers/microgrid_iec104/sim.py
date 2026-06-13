"""Simulated microgrid controller RTU over IEC 60870-5-104 (Phase 9G).

An IEC-104 controlled station: answers General Interrogation with the current
measurement dataset (frequency, PCC power, solar, load, voltage, setpoint) and the
grid-connection status, and applies single commands (breaker close/open =
grid_connect/island) and setpoint commands. Physics mirror the legacy microgrid
sim: grid-connected -> PCC tracks the setpoint and the grid holds frequency;
islanded -> PCC = 0 and residual imbalance bends frequency via droop.

Standalone:
    python -m microgrid_iec104.sim --port 2404 --common-address 1   # from drivers/
"""
from __future__ import annotations

import sys
import time
import random
import logging
import argparse

from . import models
from .transport import Iec104Server

logger = logging.getLogger("diep-driver.microgrid_iec104.sim")

NOMINAL_FREQ = 50.0
NOMINAL_VOLTAGE = 230.0
DROOP_KW_PER_HZ = 20.0  # kW imbalance that shifts islanded frequency by 1 Hz


class MicrogridRtuSim:
    def __init__(self, common_address: int = 1, host: str = "0.0.0.0", port: int = 2404):
        self.ca = common_address
        self.grid_connected = True
        self.setpoint_kw = 0.0
        self.server = Iec104Server(host=host, port=port, on_asdu=self._on_asdu)

    def start(self) -> int:
        port = self.server.start()
        logger.info("Microgrid IEC-104 RTU on %s:%s (CA=%d)", self.server.host, port, self.ca)
        return port

    def stop(self) -> None:
        self.server.stop()

    # --- physics ---------------------------------------------------------
    def _measure(self) -> dict:
        load_kw = round(random.uniform(5.0, 25.0), 2)
        solar_kw = round(random.uniform(0.0, 20.0), 2)
        net_load = load_kw - solar_kw  # + deficit / - surplus
        if self.grid_connected:
            pcc_kw = self.setpoint_kw
            frequency = round(NOMINAL_FREQ + random.uniform(-0.02, 0.02), 3)
        else:
            pcc_kw = 0.0
            frequency = round(NOMINAL_FREQ - net_load / DROOP_KW_PER_HZ, 3)
        return {
            models.IOA_FREQ: frequency,
            models.IOA_PCC: pcc_kw,
            models.IOA_SOLAR: solar_kw,
            models.IOA_LOAD: load_kw,
            models.IOA_VOLTAGE: round(NOMINAL_VOLTAGE + random.uniform(-1.5, 1.5), 2),
            models.IOA_SETPOINT: self.setpoint_kw,
        }

    # --- IEC-104 handling ------------------------------------------------
    def _send_dataset(self, peer, cot: int) -> None:
        meas = self._measure()
        peer.send_asdu(models.encode_asdu(
            models.M_ME_NC_1, cot, self.ca,
            [(ioa, models.me_nc(val)) for ioa, val in meas.items()]))
        peer.send_asdu(models.encode_asdu(
            models.M_SP_NA_1, cot, self.ca,
            [(models.IOA_GRID_CONNECTED, models.sp_na(1 if self.grid_connected else 0))]))

    def _on_asdu(self, peer, asdu: bytes) -> None:
        try:
            d = models.decode_asdu(asdu)
        except Exception:  # noqa: BLE001
            return
        tid = d["type_id"]
        if tid == models.C_IC_NA_1:
            peer.send_asdu(models.encode_asdu(models.C_IC_NA_1, models.COT_ACTCON, self.ca,
                                              [(0, models.qoi(models.QOI_STATION))]))
            self._send_dataset(peer, models.COT_INTERROGATED)
            peer.send_asdu(models.encode_asdu(models.C_IC_NA_1, models.COT_ACTTERM, self.ca,
                                              [(0, models.qoi(models.QOI_STATION))]))
        elif tid == models.C_SC_NA_1:
            ioa, val = d["objects"][0]
            if ioa == models.IOA_BREAKER:
                self.grid_connected = bool(val)
                logger.info("breaker -> %s", "CLOSED (grid_connected)" if val else "OPEN (islanded)")
            peer.send_asdu(models.encode_asdu(models.C_SC_NA_1, models.COT_ACTCON, self.ca,
                                              [(ioa, models.sc_na(val))]))
            self._send_dataset(peer, models.COT_SPONTANEOUS)
        elif tid == models.C_SE_NC_1:
            ioa, val = d["objects"][0]
            if ioa == models.IOA_CMD_SETPOINT:
                self.setpoint_kw = float(val)
                logger.info("setpoint -> %.2f kW", self.setpoint_kw)
            peer.send_asdu(models.encode_asdu(models.C_SE_NC_1, models.COT_ACTCON, self.ca,
                                              [(ioa, models.se_nc(val))]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Microgrid IEC-104 RTU simulator")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=2404)
    parser.add_argument("--common-address", type=int, default=1)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    sim = MicrogridRtuSim(common_address=args.common_address, host=args.host, port=args.port)
    sim.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sim.stop()
        print("microgrid RTU stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
