"""MDM Duplicate Detection tests."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contracts import Measurement, TelemetryEnvelope
from services.mdm.duplicates import DuplicateDetector, POLICY_CORRELATION_ONLY, POLICY_KEY_ONLY


def _envelope(**overrides):
    base = dict(
        tenant_id="tenantA", site_id="site1", device_id="METER001", meter_id="METER001",
        timestamp_utc="2026-06-25T12:00:00Z", sequence_number=0,
        correlation_id="11111111-1111-1111-1111-111111111111",
        measurements=[Measurement(measurement_type="voltage", unit="V", value=230.0)],
    )
    base.update(overrides)
    return TelemetryEnvelope(**base)


def test_first_sighting_is_not_a_duplicate():
    result = DuplicateDetector().check_and_record(_envelope())
    assert result.is_duplicate is False


def test_identical_resend_is_a_duplicate_timestamp_sequence():
    d = DuplicateDetector()
    d.check_and_record(_envelope())
    result = d.check_and_record(_envelope())
    assert result.is_duplicate is True
    assert "timestamp_sequence" in result.matched_on


def test_same_correlation_id_different_sequence_is_a_duplicate():
    d = DuplicateDetector()
    d.check_and_record(_envelope(sequence_number=0, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    result = d.check_and_record(_envelope(sequence_number=1, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    assert result.is_duplicate is True
    assert result.matched_on == ["correlation_id"]


def test_different_sequence_and_correlation_is_not_a_duplicate():
    d = DuplicateDetector()
    d.check_and_record(_envelope(sequence_number=0, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    result = d.check_and_record(_envelope(sequence_number=1, correlation_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    assert result.is_duplicate is False


def test_key_only_policy_ignores_correlation_id_collision():
    d = DuplicateDetector(policy=POLICY_KEY_ONLY)
    d.check_and_record(_envelope(sequence_number=0, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    result = d.check_and_record(_envelope(sequence_number=1, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    assert result.is_duplicate is False  # different sequence -> different key, policy ignores the id match


def test_correlation_only_policy_ignores_key_collision():
    d = DuplicateDetector(policy=POLICY_CORRELATION_ONLY)
    d.check_and_record(_envelope(sequence_number=0, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    result = d.check_and_record(_envelope(sequence_number=0, correlation_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    assert result.is_duplicate is False  # same key, but policy only looks at correlation_id


def test_bounded_cache_evicts_oldest():
    # Distinct correlation_ids so only the (timestamp,sequence) key cache is
    # under test, not correlation_id collisions across these 4 calls.
    d = DuplicateDetector(policy=POLICY_KEY_ONLY, cache_size=2)
    d.check_and_record(_envelope(sequence_number=0, correlation_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    d.check_and_record(_envelope(sequence_number=1, correlation_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    d.check_and_record(_envelope(sequence_number=2, correlation_id="cccccccc-cccc-cccc-cccc-cccccccccccc"))  # evicts sequence_number=0's key
    result = d.check_and_record(_envelope(sequence_number=0, correlation_id="dddddddd-dddd-dddd-dddd-dddddddddddd"))
    assert result.is_duplicate is False  # evicted, looks like a fresh reading again
