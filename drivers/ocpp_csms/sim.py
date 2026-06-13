"""Simulated OCPP 1.6 charge point — a WebSocket client for testing 9F.

Dials into the CSMS, sends BootNotification + StatusNotification, then streams
MeterValues reflecting a charging session, and handles the CSMS-initiated
RemoteStartTransaction / RemoteStopTransaction / SetChargingProfile commands.
No external deps, so the CSMS + charge point + selftest run anywhere.

Standalone:
    python -m ocpp_csms.sim --csms-host 127.0.0.1 --csms-port 9000 --charger-id EVSE900
"""
from __future__ import annotations

import sys
import time
import uuid
import random
import logging
import argparse
import threading

from . import models
from .transport import WebSocketClient

logger = logging.getLogger("diep-driver.ocpp.cp")


class ChargePointSim:
    def __init__(self, csms_host: str, csms_port: int, charger_id: str = "EVSE900",
                 max_power_kw: float = 22.0, interval: float = 5.0):
        self.charger_id = charger_id
        self.max_power_kw = max_power_kw
        self.interval = interval
        self.ws = WebSocketClient(csms_host, csms_port, path=charger_id,
                                  on_message=self._on_message)
        self.charging = False
        self.power_limit_kw = max_power_kw
        self.power_kw = 0.0
        self.session_energy_kwh = 0.0
        self.vehicle_soc = 35.0
        self._running = False

    # --- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self.ws.connect()
        self._call("BootNotification",
                   {"chargePointVendor": "DIEP", "chargePointModel": "SimEVSE-1"})
        self._call("StatusNotification",
                   {"connectorId": 1, "errorCode": "NoError", "status": "Available"})
        self._running = True
        threading.Thread(target=self._telemetry_loop, name="cp-telemetry", daemon=True).start()
        logger.info("charge point %s online (max %.0f kW)", self.charger_id, self.max_power_kw)

    def stop(self) -> None:
        self._running = False
        self.ws.close()

    # --- outbound (fire-and-forget CALLs) --------------------------------
    def _call(self, action: str, payload: dict) -> None:
        try:
            self.ws.send_text(models.encode_call(uuid.uuid4().hex, action, payload))
        except ConnectionError:
            pass

    def _status(self, status: str) -> None:
        self._call("StatusNotification",
                   {"connectorId": 1, "errorCode": "NoError", "status": status})

    # --- inbound CSMS commands ------------------------------------------
    def _on_message(self, text: str) -> None:
        try:
            frame = models.decode(text)
        except Exception:  # noqa: BLE001
            return
        if frame[0] != "CALL":
            return  # CALLRESULTs to our own CALLs are ignored by the sim
        unique_id, action, payload = frame[1], frame[2], frame[3]
        status = "Accepted"
        if action == "RemoteStartTransaction":
            profile = payload.get("chargingProfile")
            if profile:
                self.power_limit_kw = min(self._profile_limit_kw(profile), self.max_power_kw)
            self.charging = True
            self._status("Charging")
            self._call("StartTransaction", {"connectorId": 1, "idTag": "DIEP",
                                            "meterStart": int(self.session_energy_kwh * 1000),
                                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")})
        elif action == "RemoteStopTransaction":
            self.charging = False
            self.power_kw = 0.0
            self._status("Finishing")
            self._call("StopTransaction", {"transactionId": payload.get("transactionId", 0),
                                           "meterStop": int(self.session_energy_kwh * 1000),
                                           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")})
        elif action == "SetChargingProfile":
            profile = payload.get("csChargingProfiles", {})
            self.power_limit_kw = min(self._profile_limit_kw(profile), self.max_power_kw)
        else:
            status = "Accepted"
        try:
            self.ws.send_text(models.encode_result(unique_id, {"status": status}))
        except ConnectionError:
            pass

    @staticmethod
    def _profile_limit_kw(profile: dict) -> float:
        try:
            period = profile["chargingSchedule"]["chargingSchedulePeriod"][0]
            limit = float(period["limit"])
            unit = profile["chargingSchedule"].get("chargingRateUnit", "W")
            return limit / 1000.0 if unit == "W" else limit
        except (KeyError, IndexError, TypeError, ValueError):
            return 1e9  # no usable limit -> effectively unlimited

    # --- telemetry loop --------------------------------------------------
    def _telemetry_loop(self) -> None:
        while self._running and self.ws.open:
            if self.charging:
                soc_factor = max(0.1, (100.0 - self.vehicle_soc) / 100.0)
                self.power_kw = round(self.power_limit_kw * soc_factor * random.uniform(0.92, 1.0), 2)
                self.session_energy_kwh = round(
                    self.session_energy_kwh + self.power_kw * self.interval / 3600.0, 4)
                self.vehicle_soc = round(min(100.0, self.vehicle_soc + self.power_kw * 0.05), 2)
                if self.vehicle_soc >= 100.0:
                    self.charging = False
                    self.power_kw = 0.0
                    self._status("Finishing")
            else:
                self.power_kw = 0.0

            voltage = round(random.uniform(228, 232), 1)
            current = round(self.power_kw * 1000.0 / voltage, 2) if self.power_kw else 0.0
            meter_value = [{
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sampledValue": [
                    models.sampled_value(round(self.power_kw * 1000, 1), "Power.Active.Import", "W"),
                    models.sampled_value(voltage, "Voltage", "V"),
                    models.sampled_value(current, "Current.Import", "A"),
                    models.sampled_value(round(self.session_energy_kwh * 1000, 1),
                                         "Energy.Active.Import.Register", "Wh"),
                    models.sampled_value(self.vehicle_soc, "SoC", "Percent"),
                ],
            }]
            self._call("MeterValues", {"connectorId": 1, "meterValue": meter_value})
            self._call("Heartbeat", {})
            time.sleep(self.interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description="OCPP 1.6 charge-point simulator")
    parser.add_argument("--csms-host", default="127.0.0.1")
    parser.add_argument("--csms-port", type=int, default=9000)
    parser.add_argument("--charger-id", default="EVSE900")
    parser.add_argument("--max-power", type=float, default=22.0)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    cp = ChargePointSim(args.csms_host, args.csms_port, args.charger_id,
                        args.max_power, args.interval)
    cp.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cp.stop()
        print("charge point stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
