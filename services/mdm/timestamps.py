"""MDM Timestamp Normalization.

contracts.TelemetryEnvelope already rejects a non-UTC/naive/malformed
timestamp_utc at construction (AMI_INGEST_PHASE4_CONTRACT.md §5) — "normalize
to UTC" at this layer means tracking the three distinct clocks the contract
defines (device/gateway via timestamp_source + timestamp_utc, and ingestion —
stamped here, since MDM is its own independent MQTT consumer alongside the
ingestor, not fed through it; each consumer stamps its own receipt time) and
flagging clock drift / out-of-order arrival, which the contract intentionally
does NOT check (it validates *shape*, not *plausibility relative to other
readings*).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from contracts import TelemetryEnvelope

from .config import Settings


@dataclass
class TimestampAssessment:
    ingestion_timestamp: str
    drift_seconds: float
    is_drifted: bool
    is_out_of_order: bool


class TimestampNormalizer:
    def __init__(self, drift_threshold_s: float | None = None):
        self.drift_threshold_s = (
            drift_threshold_s if drift_threshold_s is not None else Settings.CLOCK_DRIFT_THRESHOLD_S
        )
        self._last_sequence: dict[tuple[str, str], int] = {}  # (tenant_id, device_id) -> last sequence_number

    def assess(self, envelope: TelemetryEnvelope, received_at: datetime | None = None) -> TimestampAssessment:
        received_at = received_at or datetime.now(timezone.utc)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)

        captured_at = datetime.fromisoformat(envelope.timestamp_utc.replace("Z", "+00:00"))
        drift_seconds = (received_at - captured_at).total_seconds()
        is_drifted = abs(drift_seconds) > self.drift_threshold_s

        device_key = (envelope.tenant_id, envelope.device_id)
        last_seq = self._last_sequence.get(device_key)
        is_out_of_order = last_seq is not None and envelope.sequence_number < last_seq
        # Always advance to the highest sequence_number seen, so one
        # out-of-order straggler doesn't permanently desync future checks.
        self._last_sequence[device_key] = max(last_seq or 0, envelope.sequence_number)

        envelope.ingestion_timestamp = received_at.isoformat()
        return TimestampAssessment(
            ingestion_timestamp=envelope.ingestion_timestamp,
            drift_seconds=drift_seconds,
            is_drifted=is_drifted,
            is_out_of_order=is_out_of_order,
        )
