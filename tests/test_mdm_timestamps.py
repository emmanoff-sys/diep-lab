"""MDM Timestamp Normalization tests — drift detection, out-of-order arrival,
ingestion-timestamp stamping."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import Measurement, TelemetryEnvelope
from services.mdm.timestamps import TimestampNormalizer


def _envelope(**overrides):
    base = dict(
        tenant_id="tenantA", site_id="site1", device_id="METER001", meter_id="METER001",
        timestamp_utc="2026-06-25T12:00:00Z", sequence_number=0,
        measurements=[Measurement(measurement_type="voltage", unit="V", value=230.0)],
    )
    base.update(overrides)
    return TelemetryEnvelope(**base)


def test_stamps_ingestion_timestamp():
    env = _envelope()
    assert env.ingestion_timestamp is None
    TimestampNormalizer().assess(env, datetime(2026, 6, 25, 12, 0, 1, tzinfo=timezone.utc))
    assert env.ingestion_timestamp == "2026-06-25T12:00:01+00:00"


def test_no_drift_within_threshold():
    n = TimestampNormalizer(drift_threshold_s=30)
    result = n.assess(_envelope(), datetime(2026, 6, 25, 12, 0, 5, tzinfo=timezone.utc))
    assert result.is_drifted is False
    assert result.drift_seconds == 5.0


def test_drift_beyond_threshold_flagged():
    n = TimestampNormalizer(drift_threshold_s=30)
    result = n.assess(_envelope(), datetime(2026, 6, 25, 12, 5, 0, tzinfo=timezone.utc))
    assert result.is_drifted is True
    assert result.drift_seconds == 300.0


def test_negative_drift_also_flagged():
    """Gateway clock ahead of MDM's receive time — abs() catches this too."""
    n = TimestampNormalizer(drift_threshold_s=30)
    result = n.assess(_envelope(timestamp_utc="2026-06-25T12:10:00Z"), datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc))
    assert result.is_drifted is True
    assert result.drift_seconds < 0


def test_in_order_sequence_not_flagged():
    n = TimestampNormalizer()
    n.assess(_envelope(sequence_number=0))
    result = n.assess(_envelope(sequence_number=1))
    assert result.is_out_of_order is False


def test_out_of_order_sequence_flagged():
    n = TimestampNormalizer()
    n.assess(_envelope(sequence_number=5))
    result = n.assess(_envelope(sequence_number=3))
    assert result.is_out_of_order is True


def test_out_of_order_tracking_is_per_device():
    n = TimestampNormalizer()
    n.assess(_envelope(device_id="METER001", sequence_number=10))
    result = n.assess(_envelope(device_id="METER002", sequence_number=0))
    assert result.is_out_of_order is False  # different device, independent sequence space


def test_straggler_does_not_permanently_desync_future_checks():
    n = TimestampNormalizer()
    n.assess(_envelope(sequence_number=10))
    n.assess(_envelope(sequence_number=3))   # out-of-order straggler
    result = n.assess(_envelope(sequence_number=11))
    assert result.is_out_of_order is False  # still advances relative to the highest seen (10), not the straggler (3)
