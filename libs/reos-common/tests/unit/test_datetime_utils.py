"""Unit tests for datetime utilities — WP-002-07 §29.

UTC-safe: no naive datetimes returned or accepted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from reos_common import to_iso8601, utc_now


class TestUtcNow:
    def test_returns_aware_utc(self) -> None:
        now = utc_now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_monotonic_enough(self) -> None:
        assert utc_now() <= utc_now()


class TestToIso8601:
    def test_utc_datetime_rendered(self) -> None:
        dt = datetime(2026, 7, 2, 12, 30, 45, tzinfo=UTC)
        assert to_iso8601(dt) == "2026-07-02T12:30:45+00:00"

    def test_non_utc_zone_converted_to_utc(self) -> None:
        cet = timezone(timedelta(hours=2))
        dt = datetime(2026, 7, 2, 14, 30, 45, tzinfo=cet)
        assert to_iso8601(dt) == "2026-07-02T12:30:45+00:00"

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValueError, match="Naive datetime"):
            to_iso8601(datetime(2026, 7, 2, 12, 0, 0))  # noqa: DTZ001 — deliberate naive input
