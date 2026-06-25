"""Validated internal measurement shape — the connector's own output type.
**Not** `contracts.Measurement`: the AMI telemetry contract is frozen, and
mapping an OPC UA reading into it (units, tenant/site/device identity,
envelope framing) remains future scope. This type only needs to carry what
a single OPC UA DataChange notification (or, since the post-SIT
stabilization sprint, a single MDM trusted-stream measurement — see
build_measurement_from_trusted() and mdm_consumer.py) gives us, validated,
origin-agnostic to MeasurementSink either way.
"""
from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("diep-opcua.measurement")

GOOD_STATUS_PREFIXES = ("Good",)


@dataclass
class InternalMeasurement:
    server_name: str
    node_id: str
    measurement: str
    value: object
    data_type: str
    status_code: str
    source_timestamp: str | None
    server_timestamp: str | None
    received_at: str
    valid: bool
    invalid_reason: str | None = None
    # Additive, optional: populated for MDM-trusted-stream measurements
    # (tenant_id/site_id/feeder_id/transformer_id from MDM's enrichment) --
    # absent (None) for OPC UA client-sourced measurements, which have no
    # such metadata. Carrying it here, rather than a separate side-channel,
    # is what makes "metadata propagation" concretely observable via the
    # same /health latest() surface every measurement already goes through.
    metadata: dict | None = None


def _is_numeric_finite(value) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return True  # non-numeric values (bool/str/etc handled by status code, not range)
    return math.isfinite(value)


def build_measurement(*, server_name: str, node_id: str, measurement_name: str, value,
                       data_type: str, status_code: str,
                       source_timestamp: datetime | None, server_timestamp: datetime | None,
                       received_at: datetime | None = None) -> InternalMeasurement:
    received_at = received_at or datetime.now(timezone.utc)
    valid = True
    invalid_reason = None

    if not status_code.startswith(GOOD_STATUS_PREFIXES):
        valid = False
        invalid_reason = f"status_code={status_code}"
    elif value is None:
        valid = False
        invalid_reason = "null_value"
    elif not _is_numeric_finite(value):
        valid = False
        invalid_reason = "non_finite_value"

    def _iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return InternalMeasurement(
        server_name=server_name,
        node_id=node_id,
        measurement=measurement_name,
        value=value,
        data_type=data_type,
        status_code=status_code,
        source_timestamp=_iso(source_timestamp),
        server_timestamp=_iso(server_timestamp),
        received_at=_iso(received_at),
        valid=valid,
        invalid_reason=invalid_reason,
    )


# Quality values the AMI contract considers a usable reading (status_code
# maps to "Good" for these so build_measurement()'s existing validity rule
# applies unchanged); everything else (INVALID/MISSING/COMMUNICATION_FAILURE/
# OUT_OF_RANGE/DUPLICATE) maps to a "Bad_<quality>" status_code instead.
TRUSTED_GOOD_QUALITIES = ("GOOD", "ESTIMATED", "SUBSTITUTED")


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def build_measurement_from_trusted(payload: dict, *, domain: str,
                                    received_at: datetime | None = None) -> list[InternalMeasurement]:
    """Maps one MDM "trusted" message (envelope.to_dict() plus the additive
    "mdm" key -- see services/mdm/pipeline.py) onto InternalMeasurement, one
    per measurement, so it flows through the exact same validated
    sink/health/metrics surface as an OPC UA client-sourced reading rather
    than needing a parallel one. Quality -> status_code per
    TRUSTED_GOOD_QUALITIES; tenant/site/feeder/transformer (MDM's
    enrichment) rides along in `metadata`, additive and optional."""
    device_id = payload.get("device_id", "unknown")
    server_name = f"mdm-trusted/{domain}/{device_id}"
    mdm_meta = payload.get("mdm") or {}
    device_metadata = mdm_meta.get("device_metadata")
    source_ts = _parse_iso(payload.get("timestamp_utc"))
    server_ts = _parse_iso(mdm_meta.get("processed_at"))

    out = []
    for m in payload.get("measurements", []):
        quality = m.get("quality", "GOOD")
        status_code = "Good" if quality in TRUSTED_GOOD_QUALITIES else f"Bad_{quality}"
        measurement = build_measurement(
            server_name=server_name,
            node_id=m.get("measurement_type", "unknown"),
            measurement_name=m.get("measurement_type", "unknown"),
            value=m.get("value"),
            data_type="Double",
            status_code=status_code,
            source_timestamp=source_ts,
            server_timestamp=server_ts,
            received_at=received_at,
        )
        measurement.metadata = device_metadata
        out.append(measurement)
    return out


class MeasurementSink:
    """Default sink: logs, records to a bounded per-(server, measurement)
    history for /health introspection, and tracks the latest value per key.
    Deliberately does not publish anywhere — "the connector should terminate
    [its responsibility] after producing validated internal measurements";
    wiring this to MQTT/Kafka is the next sprint (see module docstring and
    VALIDATION.md)."""

    def __init__(self, history_size: int = 50, metrics=None):
        self._history_size = history_size
        self.metrics = metrics
        self._history: dict[tuple[str, str], deque] = {}
        self._latest: dict[tuple[str, str], InternalMeasurement] = {}

    def emit(self, m: InternalMeasurement) -> None:
        key = (m.server_name, m.measurement)
        hist = self._history.setdefault(key, deque(maxlen=self._history_size))
        hist.append(m)
        self._latest[key] = m
        if m.valid:
            logger.debug("measurement %s/%s = %s", m.server_name, m.measurement, m.value)
        else:
            logger.warning("invalid measurement %s/%s: %s", m.server_name, m.measurement, m.invalid_reason)

    def latest(self) -> dict[str, dict]:
        return {
            f"{server}/{measurement}": {
                "value": m.value,
                "valid": m.valid,
                "received_at": m.received_at,
                "status_code": m.status_code,
                "source_timestamp": m.source_timestamp,
                "server_timestamp": m.server_timestamp,
                "metadata": m.metadata,
            }
            for (server, measurement), m in self._latest.items()
        }

    def history(self, server_name: str, measurement_name: str) -> list[InternalMeasurement]:
        return list(self._history.get((server_name, measurement_name), ()))
