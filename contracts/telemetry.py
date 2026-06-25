"""AMI Ingest Phase 4 — canonical telemetry envelope.

Single source of truth for the wire shape every telemetry-producing driver
(starting with drivers/dlms) and every downstream consumer (MDM, OPC UA, CIM,
ADMS) must agree on. See AMI_INGEST_PHASE4_CONTRACT.md for the full spec —
this module is that spec made enforceable.

Design note (nesting): the field list in the contract request is flat
(tenant_id, device_id, measurement_type, unit, value, quality, estimated,
...), which read literally implies one measurement per message. The existing
platform-wide Runner (drivers/diep_driver/runner.py) publishes one MQTT
message per device per read cycle carrying multiple canonical fields
(voltage, current, power_kw, frequency, ...) at once. Fanning that out to one
message per field would 4x the message rate for every existing driver
(battery, solar, charger, microgrid), not just the AMI/DLMS work this phase
is scoped to. Resolution: TelemetryEnvelope carries the envelope-level fields
once, plus a `measurements` list of Measurement (measurement_type, unit,
value, quality, estimated) — one entry per field in that cycle's reading.
Every field named in the contract request is present; they're just nested by
level (envelope vs. per-point) so per-point quality/estimated is still
possible (the whole reason a quality model exists) without changing the
platform's message-per-cycle cadence.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from .quality import Quality

# MAJOR.MINOR. MAJOR bump = breaking change (field removed/retyped/renamed).
# MINOR bump = additive only (new optional field) — see versioning policy in
# AMI_INGEST_PHASE4_CONTRACT.md §6.
SCHEMA_VERSION = "1.0"

VALID_TIMESTAMP_SOURCES = frozenset({"DEVICE", "GATEWAY", "INGEST"})


class ContractValidationError(ValueError):
    """A payload does not conform to the AMI Ingest Phase 4 contract."""


def _parse_utc(ts: str, field_name: str) -> datetime:
    if not isinstance(ts, str) or not ts:
        raise ContractValidationError(f"{field_name} must be a non-empty ISO8601 string")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} is not valid ISO8601: {ts!r}") from exc
    if dt.tzinfo is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware UTC, got naive: {ts!r}")
    if dt.utcoffset().total_seconds() != 0:
        raise ContractValidationError(f"{field_name} must be UTC (offset +00:00), got: {ts!r}")
    return dt


def is_version_compatible(version: str, *, against: str = SCHEMA_VERSION) -> bool:
    """Same MAJOR version = compatible (minor versions are additive-only per
    the versioning policy, so an older/newer MINOR within the same MAJOR is
    always safe to consume)."""
    try:
        major = version.split(".", 1)[0]
        against_major = against.split(".", 1)[0]
    except AttributeError:
        return False
    return major == against_major


@dataclass
class Measurement:
    measurement_type: str   # e.g. "voltage", "active_power", "frequency" — see contract doc §3 for the registry
    unit: str                # e.g. "V", "kW", "Hz" — UCUM-style short unit codes
    value: float
    quality: Quality = Quality.GOOD
    estimated: bool = False

    def __post_init__(self):
        if not self.measurement_type:
            raise ContractValidationError("measurement_type is required")
        if not self.unit:
            raise ContractValidationError("unit is required")
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise ContractValidationError(f"value must be numeric, got {self.value!r}")
        if not isinstance(self.quality, Quality):
            try:
                self.quality = Quality(self.quality)
            except ValueError as exc:
                raise ContractValidationError(f"invalid quality: {self.quality!r}") from exc
        # estimated is independent of quality (a SUBSTITUTED value is also "not
        # measured"), but ESTIMATED quality always implies estimated=True.
        if self.quality is Quality.ESTIMATED and not self.estimated:
            self.estimated = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quality"] = self.quality.value
        return d


@dataclass
class TelemetryEnvelope:
    tenant_id: str
    site_id: str
    device_id: str
    meter_id: str
    timestamp_utc: str              # device/gateway capture time, ISO8601 UTC
    measurements: list[Measurement]
    timestamp_source: str = "GATEWAY"   # DEVICE | GATEWAY | INGEST — see contract doc §5
    source_protocol: str = "dlms"
    source_system: str = "ami-ingest"
    sequence_number: int = 0
    schema_version: str = SCHEMA_VERSION
    ingestion_timestamp: str | None = None   # set by the ingestor, not the driver
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        for f in ("tenant_id", "site_id", "device_id", "meter_id"):
            if not getattr(self, f):
                raise ContractValidationError(f"{f} is required")
        _parse_utc(self.timestamp_utc, "timestamp_utc")
        if self.ingestion_timestamp is not None:
            _parse_utc(self.ingestion_timestamp, "ingestion_timestamp")
        if self.timestamp_source not in VALID_TIMESTAMP_SOURCES:
            raise ContractValidationError(
                f"timestamp_source must be one of {sorted(VALID_TIMESTAMP_SOURCES)}, got {self.timestamp_source!r}"
            )
        if not isinstance(self.sequence_number, int) or isinstance(self.sequence_number, bool) or self.sequence_number < 0:
            raise ContractValidationError(f"sequence_number must be a non-negative int, got {self.sequence_number!r}")
        if not is_version_compatible(self.schema_version):
            raise ContractValidationError(
                f"schema_version {self.schema_version!r} is not compatible with {SCHEMA_VERSION} "
                "(major version mismatch — see versioning policy)"
            )
        if not self.measurements:
            raise ContractValidationError("measurements must contain at least one entry")
        self.measurements = [
            m if isinstance(m, Measurement) else Measurement(**m) for m in self.measurements
        ]
        seen = set()
        for m in self.measurements:
            if m.measurement_type in seen:
                raise ContractValidationError(
                    f"duplicate measurement_type {m.measurement_type!r} within one envelope "
                    "— each measurement_type must appear at most once per envelope"
                )
            seen.add(m.measurement_type)

    def stamp_ingestion_time(self) -> None:
        """Called by the ingestor (never the driver) on receipt."""
        self.ingestion_timestamp = datetime.now(timezone.utc).isoformat()

    def dedup_key(self) -> tuple:
        """Identity for duplicate detection per contract doc §5 (late-arriving /
        redelivered messages): same tenant+device+timestamp+sequence_number is
        the same reading, regardless of transport-level retries."""
        return (self.tenant_id, self.device_id, self.timestamp_utc, self.sequence_number)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["measurements"] = [m.to_dict() for m in self.measurements]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "TelemetryEnvelope":
        data = dict(data)
        measurements = data.pop("measurements", [])
        return cls(measurements=[Measurement(**m) for m in measurements], **data)

    @classmethod
    def from_json(cls, raw: str) -> "TelemetryEnvelope":
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(f"not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ContractValidationError("payload must be a JSON object")
        try:
            return cls.from_dict(data)
        except TypeError as exc:
            raise ContractValidationError(f"missing/unexpected field(s): {exc}") from exc
