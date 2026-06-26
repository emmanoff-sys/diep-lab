"""Runner — the shared edge loop that drives a BaseDriver.

Owns the MQTT plumbing so concrete drivers only implement protocol logic:
  - periodically: read_telemetry -> normalize -> publish to diep/<domain>/<id>
  - on command:   parse .../cmd -> execute_command -> publish .../ack

This mirrors the simulator + dispatcher contract exactly, so a driver is a
drop-in replacement for a simulator. New code only; runs on the edge gateway.
"""
from __future__ import annotations

import json
import time
import logging
from collections import deque
from datetime import datetime, timezone

from .base import BaseDriver, CommandResult
from .mqtt_client import MqttTransport

logger = logging.getLogger("diep-driver.runner")

_envelope_seq: dict[str, int] = {}  # device_id -> next sequence_number, in-process only


class Runner:
    def __init__(self, driver: BaseDriver, transport: MqttTransport | None = None,
                 telemetry_interval: int = 5, buffer_size: int = 10000):
        self.driver = driver
        self.interval = telemetry_interval
        self.transport = transport or MqttTransport(client_id=f"driver-{driver.device_id}")
        # Phase 9A store-and-forward: when the broker/platform is unreachable, buffer
        # timestamped telemetry on the edge (bounded ring) and replay it on reconnect,
        # so a remote site survives transient outages without losing readings.
        self._buffer: deque[str] = deque(maxlen=buffer_size)

    def _on_command(self, client, userdata, msg):
        try:
            cmd = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("Unparseable command on %s: %s", msg.topic, exc)
            return
        command_id = cmd.get("command_id")
        command_type = cmd.get("command_type")
        params = cmd.get("params") or {}
        logger.info("Command %s (%s) for %s", command_type, command_id, self.driver.device_id)
        try:
            result = self.driver.execute_command(command_type, params)
        except NotImplementedError:
            result = CommandResult("FAILED", "driver not yet implemented")
        except Exception as exc:  # noqa: BLE001 — surface device errors as FAILED ack
            result = CommandResult("FAILED", str(exc))
        ack = {
            "command_id": command_id,
            "device_id": self.driver.device_id,
            "status": result.status,
            "error": result.error,
            "acked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.transport.publish(self.driver.ack_topic, json.dumps(ack), qos=1)

    def run(self):
        self.driver.connect()
        self.transport.connect()
        self.transport.subscribe(self.driver.cmd_topic, self._on_command, qos=1)
        logger.info("Runner started for %s on %s", self.driver.device_id, self.driver.base_topic)
        try:
            while True:
                try:
                    native = self.driver.read_telemetry()
                    payload = self.driver.normalize(native)
                    if self.driver.use_contract_envelope:
                        message = self._build_envelope(payload)
                    else:
                        payload["device_id"] = self.driver.device_id
                        # Stamp capture time so buffered readings keep their real timestamp.
                        payload["time"] = datetime.now(timezone.utc).isoformat()
                        message = json.dumps(payload)
                    self._publish_telemetry(message)
                except NotImplementedError:
                    logger.warning("read_telemetry not implemented for %s", self.driver.device_id)
                except Exception as exc:  # noqa: BLE001
                    logger.error("telemetry read failed for %s: %s", self.driver.device_id, exc)
                time.sleep(self.interval)
        finally:
            self.transport.disconnect()
            self.driver.disconnect()

    def _build_envelope(self, normalized: dict) -> str:
        """AMI Ingest Phase 4 (contracts/telemetry.py) opt-in path — see
        BaseDriver.use_contract_envelope. Imported lazily so a driver that
        never opts in doesn't need `contracts` on its sys.path."""
        from contracts import Measurement, TelemetryEnvelope

        units = self.driver.measurement_units()
        now = datetime.now(timezone.utc).isoformat()
        device_id = self.driver.device_id
        seq = _envelope_seq.get(device_id, 0)
        _envelope_seq[device_id] = seq + 1
        # Only emit a Measurement for fields this driver actually has a unit
        # for (measurement_units() is the source of truth for "measured by
        # this device"). normalize() pads every canonical field to 0.0 even
        # for fields a given driver doesn't read — looping over normalized's
        # full 8 keys would fabricate phantom 0.0 readings for unmeasured
        # fields, the exact "0.0 indistinguishable from a real zero" gap
        # AMI_INGEST_PHASE4_CONTRACT.md calls out as a legacy ad-hoc issue.
        measurements = [
            Measurement(measurement_type=field, unit=unit, value=normalized[field])
            for field, unit in units.items()
            if field in normalized and isinstance(normalized[field], (int, float))
            and not isinstance(normalized[field], bool)
        ]
        envelope = TelemetryEnvelope(
            tenant_id=self.driver.tenant_id,
            site_id=self.driver.site_id,
            device_id=device_id,
            meter_id=self.driver.meter_id,
            timestamp_utc=now,
            timestamp_source="GATEWAY",
            source_protocol=self.driver.protocol,
            source_system="ami-ingest",
            sequence_number=seq,
            measurements=measurements,
        )
        return envelope.to_json()

    def _publish_telemetry(self, message: str) -> None:
        """Store-and-forward: replay the buffer when connected, else buffer this reading."""
        if self.transport.connected:
            if self._buffer:
                n = len(self._buffer)
                while self._buffer:
                    self.transport.publish(self.driver.base_topic, self._buffer.popleft())
                logger.info("replayed %d buffered reading(s) for %s after reconnect",
                            n, self.driver.device_id)
            self.transport.publish(self.driver.base_topic, message)
        else:
            self._buffer.append(message)
            if len(self._buffer) % 20 == 1:
                logger.warning("offline — buffering telemetry for %s (%d held)",
                               self.driver.device_id, len(self._buffer))
