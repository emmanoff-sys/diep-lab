"""MDM Quality Engine.

contracts.Quality (frozen, see AMI_INGEST_PHASE4_CONTRACT.md §4) defines the
8-flag vocabulary; this engine is what actually *applies* it past whatever
the driver already set.

"Never silently overwrite quality flags" (spec requirement) is implemented
as: MDM only ever escalates FROM GOOD — if the driver already flagged
something non-GOOD (ESTIMATED, SUBSTITUTED, ...), MDM leaves it untouched
and does not second-guess it. Every escalation MDM does perform is returned
as an explicit QualityTransition record (not just mutated in place), so the
change is always attributable and audit-loggable — "silent" is the part
that's disallowed, not "MDM may never change anything."
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from contracts import Measurement, Quality

from .config import Settings

REASON_NON_FINITE = "non_finite_value"
REASON_OUT_OF_RANGE = "out_of_range"


@dataclass(frozen=True)
class QualityTransition:
    measurement_type: str
    original_quality: Quality
    new_quality: Quality
    reason: str


class QualityAssessor:
    def __init__(self, range_limits: dict[str, tuple[float, float]] | None = None):
        self.range_limits = range_limits if range_limits is not None else Settings.RANGE_LIMITS

    def assess(self, measurement: Measurement) -> tuple[Measurement, QualityTransition | None]:
        if measurement.quality is not Quality.GOOD:
            # Already flagged by the driver — never overwritten, per the
            # "never silently overwrite" requirement.
            return measurement, None

        if not math.isfinite(measurement.value):
            new = replace(measurement, quality=Quality.INVALID)
            return new, QualityTransition(
                measurement.measurement_type, Quality.GOOD, Quality.INVALID, REASON_NON_FINITE
            )

        limits = self.range_limits.get(measurement.measurement_type)
        if limits is not None:
            lo, hi = limits
            if not (lo <= measurement.value <= hi):
                new = replace(measurement, quality=Quality.OUT_OF_RANGE)
                return new, QualityTransition(
                    measurement.measurement_type, Quality.GOOD, Quality.OUT_OF_RANGE, REASON_OUT_OF_RANGE
                )

        return measurement, None
