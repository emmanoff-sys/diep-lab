"""OCPP 1.6 Central System (CSMS) — the Phase 9F EV-charger "driver".

ARCHITECTURAL EXCEPTION (documented in the stub and the 9D report): OCPP chargers
are WebSocket **clients** that dial into a CSMS **server**. So this is not a
BaseDriver poll loop — it is an event-driven CSMS that bridges OCPP <-> DIEP MQTT:

  inbound  BootNotification / StatusNotification / StartTransaction / MeterValues
           / StopTransaction / Heartbeat   ->  canonical telemetry on diep/charger/<id>
  outbound start_charging / stop_charging / set_limit (from diep/charger/<id>/cmd)
           ->  RemoteStartTransaction / RemoteStopTransaction / SetChargingProfile
           ->  ack on diep/charger/<id>/ack

`Csms` is the transport+protocol core (testable with no broker). `CsmsMqttBridge`
wires it to the platform via the SDK's MqttTransport + canonical normalize, so the
charger appears to the ingestor / dispatcher / twins / DERMS exactly like any device.
"""
from __future__ import annotations

import json
import time
import uuid
import logging
import threading
from datetime import datetime, timezone

from diep_driver import normalize_canonical
from diep_driver.registry import register
from diep_driver import BaseDriver, CommandResult

from . import models
from .transport import WebSocketServer

logger = logging.getLogger("diep-driver.ocpp.csms")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ChargePoint:
    """CSMS-side state for one connected charge point."""
    __slots__ = ("ws", "charger_id", "status", "transaction_id", "vendor", "model")

    def __init__(self, ws, charger_id):
        self.ws = ws
        self.charger_id = charger_id
        self.status = "Unavailable"
        self.transaction_id = 0
        self.vendor = ""
        self.model = ""


class Csms:
    """OCPP 1.6 Central System core. on_telemetry(charger_id, native_dict) is called
    whenever a charge point reports MeterValues; on_status(charger_id, status) on
    connector status changes."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9000,
                 on_telemetry=None, on_status=None):
        self.on_telemetry = on_telemetry
        self.on_status = on_status
        self.server = WebSocketServer(host=host, port=port,
                                      on_connect=self._on_connect,
                                      on_message=self._on_message,
                                      on_close=self._on_close)
        self._cps: dict[str, _ChargePoint] = {}
        self._txn_counter = 1000
        self._pending: dict[str, dict] = {}   # uniqueId -> {event, result}
        self._lock = threading.Lock()

    # --- lifecycle -------------------------------------------------------
    def start(self) -> int:
        port = self.server.start()
        logger.info("CSMS listening on ws://%s:%s", self.server.host, port)
        return port

    def stop(self) -> None:
        self.server.stop()

    def connected_chargers(self) -> list[str]:
        return list(self._cps)

    # --- WS callbacks ----------------------------------------------------
    def _on_connect(self, ws) -> None:
        self._cps[ws.charger_id] = _ChargePoint(ws, ws.charger_id)
        logger.info("charge point connected: %s", ws.charger_id)

    def _on_close(self, ws) -> None:
        self._cps.pop(ws.charger_id, None)
        logger.info("charge point disconnected: %s", ws.charger_id)

    def _on_message(self, ws, text: str) -> None:
        try:
            frame = models.decode(text)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("bad OCPP frame from %s: %s", ws.charger_id, exc)
            return
        kind = frame[0]
        if kind == "CALL":
            self._handle_call(ws, frame[1], frame[2], frame[3])
        elif kind == "CALLRESULT":
            self._resolve_pending(frame[1], ok=True, payload=frame[2])
        elif kind == "CALLERROR":
            self._resolve_pending(frame[1], ok=False, payload={"error": frame[2]})

    # --- inbound CP-initiated actions ------------------------------------
    def _handle_call(self, ws, unique_id: str, action: str, payload: dict) -> None:
        cp = self._cps.get(ws.charger_id)
        result: dict = {}
        if action == "BootNotification":
            if cp:
                cp.vendor = payload.get("chargePointVendor", "")
                cp.model = payload.get("chargePointModel", "")
            result = {"currentTime": _utc_now(), "interval": 30, "status": "Accepted"}
        elif action == "Heartbeat":
            result = {"currentTime": _utc_now()}
        elif action == "StatusNotification":
            status = payload.get("status", "Available")
            if cp:
                cp.status = status
            if self.on_status:
                self.on_status(ws.charger_id, status)
            result = {}
        elif action == "StartTransaction":
            with self._lock:
                self._txn_counter += 1
                txn = self._txn_counter
            if cp:
                cp.transaction_id = txn
            result = {"transactionId": txn, "idTagInfo": {"status": "Accepted"}}
        elif action == "StopTransaction":
            if cp:
                cp.transaction_id = 0
            result = {"idTagInfo": {"status": "Accepted"}}
        elif action == "MeterValues":
            native = models.meter_values_to_native(payload.get("meterValue", []))
            if cp:
                native.setdefault("connector_status", cp.status)
            if self.on_telemetry and native:
                self.on_telemetry(ws.charger_id, native)
            result = {}
        else:
            # Unknown but well-formed: accept with empty result.
            result = {}
        try:
            ws.send_text(models.encode_result(unique_id, result))
        except ConnectionError:
            pass

    # --- outbound CSMS-initiated commands --------------------------------
    def _call(self, charger_id: str, action: str, payload: dict, timeout: float = 5.0):
        cp = self._cps.get(charger_id)
        if cp is None:
            return False, {"error": f"charge point '{charger_id}' not connected"}
        unique_id = uuid.uuid4().hex
        event = threading.Event()
        self._pending[unique_id] = {"event": event, "ok": False, "payload": {}}
        try:
            cp.ws.send_text(models.encode_call(unique_id, action, payload))
        except ConnectionError as exc:
            self._pending.pop(unique_id, None)
            return False, {"error": str(exc)}
        if not event.wait(timeout):
            self._pending.pop(unique_id, None)
            return False, {"error": f"timeout awaiting {action} result"}
        pend = self._pending.pop(unique_id, {})
        return pend.get("ok", False), pend.get("payload", {})

    def _resolve_pending(self, unique_id: str, ok: bool, payload: dict) -> None:
        pend = self._pending.get(unique_id)
        if pend:
            pend["ok"] = ok
            pend["payload"] = payload
            pend["event"].set()

    def send_command(self, charger_id: str, command_type: str, params: dict):
        """Translate a DIEP command to OCPP and return (status, error)."""
        params = params or {}
        cp = self._cps.get(charger_id)
        if cp is None:
            return "FAILED", f"charge point '{charger_id}' not connected"

        if command_type == "start_charging":
            payload = {"idTag": "DIEP", "connectorId": 1}
            limit_kw = params.get("max_power_kw")
            if limit_kw is not None:
                payload["chargingProfile"] = _charging_profile(float(limit_kw))
            ok, resp = self._call(charger_id, "RemoteStartTransaction", payload)
            return _ack_from(ok, resp)

        if command_type == "stop_charging":
            txn = cp.transaction_id or 0
            ok, resp = self._call(charger_id, "RemoteStopTransaction", {"transactionId": txn})
            return _ack_from(ok, resp)

        if command_type == "set_limit":
            if "max_power_kw" not in params:
                return "FAILED", "set_limit requires params.max_power_kw"
            payload = {"connectorId": 1, "csChargingProfiles":
                       _charging_profile(float(params["max_power_kw"]))}
            ok, resp = self._call(charger_id, "SetChargingProfile", payload)
            return _ack_from(ok, resp)

        return "FAILED", f"unsupported command '{command_type}'"


def _charging_profile(limit_kw: float) -> dict:
    return {
        "chargingProfileId": 1, "stackLevel": 0,
        "chargingProfilePurpose": "TxDefaultProfile", "chargingProfileKind": "Absolute",
        "chargingSchedule": {
            "chargingRateUnit": "W",
            "chargingSchedulePeriod": [{"startPeriod": 0, "limit": limit_kw * 1000.0}],
        },
    }


def _ack_from(ok: bool, resp: dict):
    if not ok:
        return "FAILED", resp.get("error", "call error")
    status = (resp or {}).get("status", "Accepted")
    if status in ("Accepted", "Scheduled"):
        return "ACKED", None
    return "FAILED", f"charge point returned status '{status}'"


# ---------------------------------------------------------------------------
# MQTT bridge — connects the CSMS core to the DIEP data/command plane.
# ---------------------------------------------------------------------------
class CsmsMqttBridge:
    domain = "charger"

    def __init__(self, host: str = "0.0.0.0", port: int = 9000, transport=None):
        self.csms = Csms(host=host, port=port,
                         on_telemetry=self._publish_telemetry, on_status=None)
        self._latest_status: dict[str, str] = {}
        if transport is None:
            from diep_driver.mqtt_client import MqttTransport
            transport = MqttTransport(client_id="ocpp-csms")
        self.transport = transport

    def run(self) -> None:
        self.csms.start()
        self.transport.connect()
        # One subscription covers every charge point's command topic.
        self.transport.subscribe("diep/charger/+/cmd", self._on_command, qos=1)
        logger.info("CSMS MQTT bridge running; awaiting charge points + commands")
        try:
            while True:
                time.sleep(1)
        finally:
            self.transport.disconnect()
            self.csms.stop()

    def _publish_telemetry(self, charger_id: str, native: dict) -> None:
        canonical = normalize_canonical(native, aliases={})
        # A charger draws from the grid; mirror that into the canonical grid field.
        canonical["grid_import_kw"] = max(0.0, canonical.get("power_kw", 0.0))
        for k in ("session_energy_kwh", "vehicle_soc", "connector_status"):
            if k in native:
                canonical[k] = native[k]
        canonical["device_id"] = charger_id
        self.transport.publish(f"diep/charger/{charger_id}", json.dumps(canonical))

    def _on_command(self, client, userdata, msg) -> None:
        try:
            cmd = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("unparseable command on %s: %s", msg.topic, exc)
            return
        charger_id = cmd.get("device_id") or msg.topic.split("/")[2]
        # Only handle chargers actually connected to THIS CSMS, so we coexist with
        # other charger devices on the same broker without double-acking their commands.
        if charger_id not in self.csms.connected_chargers():
            return
        command_id = cmd.get("command_id")
        command_type = cmd.get("command_type")
        params = cmd.get("params") or {}
        logger.info("command %s (%s) for %s", command_type, command_id, charger_id)
        status, error = self.csms.send_command(charger_id, command_type, params)
        ack = {
            "command_id": command_id, "device_id": charger_id,
            "status": status, "error": error,
            "acked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.transport.publish(f"diep/charger/{charger_id}/ack", json.dumps(ack), qos=1)


# Registry entry for discoverability/parity. The CSMS runs as a service (see
# __main__ / docker-compose-ocpp.yml), not via the per-device polling Runner —
# connect()/read_telemetry() intentionally signpost the server-role exception.
@register("ocpp_csms")
class OcppCsmsDriver(BaseDriver):
    domain = "charger"

    def connect(self) -> None:
        raise NotImplementedError(
            "OCPP is a CSMS server role — run CsmsMqttBridge as a service, not the poll Runner")

    def read_telemetry(self) -> dict:
        raise NotImplementedError("telemetry is pushed by chargers via MeterValues")

    def execute_command(self, command_type: str, params: dict) -> CommandResult:
        raise NotImplementedError("commands are handled by the CSMS bridge")

    def supported_commands(self) -> set[str]:
        return {"start_charging", "stop_charging", "set_limit"}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="OCPP 1.6 CSMS + MQTT bridge")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")
    CsmsMqttBridge(host=args.host, port=args.port).run()


if __name__ == "__main__":
    main()
