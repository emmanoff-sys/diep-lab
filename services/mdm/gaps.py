"""MDM Gap Detection.

Tracks, per (tenant_id, device_id, measurement_type), the last-seen
timestamp_utc. A gap is declared when the elapsed time since the last
reading exceeds the configured expected interval by more than
GAP_TOLERANCE_MULTIPLIER — see config.py.

A gap is a *quality event* (a GapEvent), not a Measurement with quality=
MISSING: there is no measurement object for an interval that never arrived,
so "MISSING" (contracts.Quality.MISSING) is the right vocabulary but a
GapEvent is the right carrier — nothing downstream should expect a
Measurement to materialize for the missed interval itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from contracts import TelemetryEnvelope

from .config import Settings


@dataclass(frozen=True)
class GapEvent:
    tenant_id: str
    device_id: str
    measurement_type: str
    last_seen_at: str
    current_at: str
    gap_seconds: float
    expected_interval_s: float
    estimated_missed_samples: int


class GapDetector:
    def __init__(
        self,
        expected_intervals: dict[str, float] | None = None,
        default_interval_s: float | None = None,
        tolerance_multiplier: float | None = None,
    ):
        self.expected_intervals = (
            expected_intervals if expected_intervals is not None else Settings.expected_intervals()
        )
        self.default_interval_s = (
            default_interval_s if default_interval_s is not None else Settings.DEFAULT_EXPECTED_INTERVAL_S
        )
        self.tolerance_multiplier = (
            tolerance_multiplier if tolerance_multiplier is not None else Settings.GAP_TOLERANCE_MULTIPLIER
        )
        self._last_seen: dict[tuple[str, str, str], datetime] = {}

    def _expected_interval(self, measurement_type: str) -> float:
        return self.expected_intervals.get(measurement_type, self.default_interval_s)

    def check(self, envelope: TelemetryEnvelope) -> list[GapEvent]:
        current_at = datetime.fromisoformat(envelope.timestamp_utc.replace("Z", "+00:00"))
        events: list[GapEvent] = []
        for m in envelope.measurements:
            key = (envelope.tenant_id, envelope.device_id, m.measurement_type)
            last_seen = self._last_seen.get(key)
            expected = self._expected_interval(m.measurement_type)
            if last_seen is not None:
                gap_seconds = (current_at - last_seen).total_seconds()
                if gap_seconds > expected * self.tolerance_multiplier:
                    events.append(GapEvent(
                        tenant_id=envelope.tenant_id,
                        device_id=envelope.device_id,
                        measurement_type=m.measurement_type,
                        last_seen_at=last_seen.isoformat(),
                        current_at=current_at.isoformat(),
                        gap_seconds=gap_seconds,
                        expected_interval_s=expected,
                        estimated_missed_samples=max(0, round(gap_seconds / expected) - 1),
                    ))
            self._last_seen[key] = current_at
        return events
