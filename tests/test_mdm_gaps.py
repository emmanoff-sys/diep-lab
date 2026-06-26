"""MDM Gap Detection tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import Measurement, TelemetryEnvelope
from services.mdm.gaps import GapDetector


def _envelope(timestamp_utc, measurement_types=("voltage",)):
    return TelemetryEnvelope(
        tenant_id="tenantA", site_id="site1", device_id="METER001", meter_id="METER001",
        timestamp_utc=timestamp_utc,
        measurements=[Measurement(measurement_type=t, unit="V", value=1.0) for t in measurement_types],
    )


def test_first_reading_no_gap():
    d = GapDetector(default_interval_s=5, tolerance_multiplier=2.0)
    events = d.check(_envelope("2026-06-25T12:00:00Z"))
    assert events == []


def test_reading_within_expected_interval_no_gap():
    d = GapDetector(default_interval_s=5, tolerance_multiplier=2.0)
    d.check(_envelope("2026-06-25T12:00:00Z"))
    events = d.check(_envelope("2026-06-25T12:00:05Z"))
    assert events == []


def test_gap_beyond_tolerance_detected():
    d = GapDetector(default_interval_s=5, tolerance_multiplier=2.0)
    d.check(_envelope("2026-06-25T12:00:00Z"))
    events = d.check(_envelope("2026-06-25T12:01:00Z"))  # 60s gap, threshold is 10s
    assert len(events) == 1
    assert events[0].measurement_type == "voltage"
    assert events[0].gap_seconds == 60.0
    assert events[0].estimated_missed_samples == 11  # 60/5 - 1


def test_per_measurement_type_expected_interval():
    d = GapDetector(expected_intervals={"voltage": 60}, default_interval_s=5, tolerance_multiplier=2.0)
    d.check(_envelope("2026-06-25T12:00:00Z"))
    events = d.check(_envelope("2026-06-25T12:01:30Z"))  # 90s, within 60*2=120 tolerance
    assert events == []


def test_gap_tracked_independently_per_measurement_type():
    d = GapDetector(default_interval_s=5, tolerance_multiplier=2.0)
    d.check(_envelope("2026-06-25T12:00:00Z", measurement_types=("voltage", "current")))
    # Only "voltage" arrives in the next reading — "current" isn't checked
    # again until it actually shows up; no event for a type that's simply absent.
    events = d.check(_envelope("2026-06-25T12:00:05Z", measurement_types=("voltage",)))
    assert events == []


def test_gap_tracked_independently_per_device():
    d = GapDetector(default_interval_s=5, tolerance_multiplier=2.0)
    d.check(TelemetryEnvelope(
        tenant_id="tenantA", site_id="site1", device_id="METER001", meter_id="METER001",
        timestamp_utc="2026-06-25T12:00:00Z",
        measurements=[Measurement(measurement_type="voltage", unit="V", value=1.0)],
    ))
    events = d.check(TelemetryEnvelope(
        tenant_id="tenantA", site_id="site1", device_id="METER002", meter_id="METER002",
        timestamp_utc="2026-06-25T12:05:00Z",
        measurements=[Measurement(measurement_type="voltage", unit="V", value=1.0)],
    ))
    assert events == []  # first sighting for METER002, not a gap
