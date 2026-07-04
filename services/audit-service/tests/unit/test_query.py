"""Unit tests: query validation logic in AuditService (ENG-SPEC-005-04 §26.1 / §11.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from audit_service.core.exceptions import (
    AuditQueryDateRangeTooLarge,
    AuditQueryInvalidDateRange,
    AuditQueryInvalidDatetime,
)
from audit_service.domain.services import AuditService


class _FakeSession:
    pass


class TestDateRangeValidation:
    def _svc(self) -> AuditService:
        return AuditService(_FakeSession())  # type: ignore[arg-type]

    def test_date_to_before_date_from_raises(self) -> None:
        svc = self._svc()
        now = datetime.now(UTC)
        with pytest.raises(AuditQueryInvalidDateRange):
            svc._resolve_date_range(now, now - timedelta(days=1))

    def test_range_exceeding_365_days_raises(self) -> None:
        svc = self._svc()
        date_from = datetime.now(UTC) - timedelta(days=400)
        date_to = datetime.now(UTC)
        with pytest.raises(AuditQueryDateRangeTooLarge):
            svc._resolve_date_range(date_from, date_to)

    def test_naive_date_from_raises(self) -> None:
        svc = self._svc()
        with pytest.raises(AuditQueryInvalidDatetime):
            svc._resolve_date_range(datetime(2026, 1, 1), None)

    def test_naive_date_to_raises(self) -> None:
        svc = self._svc()
        with pytest.raises(AuditQueryInvalidDatetime):
            svc._resolve_date_range(None, datetime(2026, 7, 4))

    def test_none_dates_use_defaults(self) -> None:
        from audit_service.config import settings
        svc = self._svc()
        df, dt = svc._resolve_date_range(None, None)
        expected_from = datetime.now(UTC) - timedelta(days=settings.QUERY_DEFAULT_DATE_RANGE_DAYS)
        assert abs((df - expected_from).total_seconds()) < 2
        assert dt.tzinfo is not None

    def test_valid_range_accepted(self) -> None:
        svc = self._svc()
        df = datetime.now(UTC) - timedelta(days=7)
        dt = datetime.now(UTC)
        resolved_from, resolved_to = svc._resolve_date_range(df, dt)
        assert resolved_from == df
        assert resolved_to == dt

    def test_exact_365_days_accepted(self) -> None:
        svc = self._svc()
        dt = datetime.now(UTC)
        df = dt - timedelta(days=365)
        resolved_from, resolved_to = svc._resolve_date_range(df, dt)
        assert resolved_from == df
