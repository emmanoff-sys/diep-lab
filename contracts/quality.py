"""Canonical quality flag for every measurement in the telemetry contract.

This is the cross-layer correctness contract PLANNING.md §3 calls out as a
hard requirement: ADMS state estimation must not silently treat an
ESTIMATED/SUBSTITUTED reading as ground truth. The flag is mandatory on every
Measurement (see telemetry.py) so it can never be dropped between AMI Ingest,
MDM, and ADMS.
"""
from __future__ import annotations

from enum import Enum


class Quality(str, Enum):
    GOOD = "GOOD"                                   # device-reported, in-range, on time
    ESTIMATED = "ESTIMATED"                          # interpolated/inferred, not device-measured
    SUBSTITUTED = "SUBSTITUTED"                      # operator/default value stood in for a real reading
    INVALID = "INVALID"                              # device reported a value but it fails validation
    MISSING = "MISSING"                              # no value available for this measurement/interval
    COMMUNICATION_FAILURE = "COMMUNICATION_FAILURE"  # could not reach the device/gateway
    OUT_OF_RANGE = "OUT_OF_RANGE"                    # value present but outside the configured physical range
    DUPLICATE = "DUPLICATE"                          # identical (device_id, measurement_type, timestamp_utc, sequence_number) already seen

    @property
    def is_measured(self) -> bool:
        """True only for GOOD — every other flag means "not ground truth"."""
        return self is Quality.GOOD

    @property
    def is_usable_for_billing(self) -> bool:
        """GOOD or SUBSTITUTED (an operator-approved stand-in) only. MDM consults
        this; ADMS state estimation should additionally gate on `is_measured`."""
        return self in (Quality.GOOD, Quality.SUBSTITUTED)
