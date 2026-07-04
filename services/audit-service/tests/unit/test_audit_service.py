"""Unit tests: AuditService business logic (ENG-SPEC-005-04 §26.1).

Uses mock repository — integration tests use real DB (STANDARDS.md §7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from audit_service.core.exceptions import AuditEventDuplicateError, AuditEventNotFoundError
from audit_service.domain.services import AuditService


def _base_event(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "event_id": uuid4(),
        "event_type": "auth.login.success",
        "actor_type": "user",
        "actor_id": uuid4(),
        "action": "login",
        "resource_type": "session",
        "outcome": "success",
        "correlation_id": uuid4(),
        "service_name": "identity-service",
        "timestamp_utc": datetime.now(UTC),
        "schema_version": 1,
    }
    base.update(overrides)
    return base


class TestWriteEvent:
    @pytest.mark.asyncio
    async def test_write_calls_repo_and_commits(self) -> None:
        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_event = MagicMock()
        mock_repo.get_last_event_hash = AsyncMock(return_value=None)
        mock_repo.write_event = AsyncMock(return_value=mock_event)

        with patch("audit_service.domain.services.AuditEventRepository", return_value=mock_repo):
            svc = AuditService(mock_session)
            result = await svc.write_event(_base_event())

        mock_repo.write_event.assert_called_once()
        mock_session.commit.assert_called_once()
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_duplicate_event_id_raises_audit_event_duplicate(self) -> None:
        from sqlalchemy import exc as sa_exc

        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.get_last_event_hash = AsyncMock(return_value=None)

        integrity_error = sa_exc.IntegrityError(
            "uq_audit_events_event_id", {}, Exception("duplicate key")
        )
        mock_repo.write_event = AsyncMock(side_effect=integrity_error)

        with patch("audit_service.domain.services.AuditEventRepository", return_value=mock_repo):
            svc = AuditService(mock_session)
            event_data = _base_event()
            with pytest.raises(AuditEventDuplicateError):
                await svc.write_event(event_data)


class TestGetEvent:
    @pytest.mark.asyncio
    async def test_returns_event_when_found(self) -> None:
        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_event = MagicMock()
        mock_repo.get_event_by_id = AsyncMock(return_value=mock_event)

        with patch("audit_service.domain.services.AuditEventRepository", return_value=mock_repo):
            svc = AuditService(mock_session)
            result = await svc.get_event(uuid4())

        assert result == mock_event

    @pytest.mark.asyncio
    async def test_raises_not_found_when_none(self) -> None:
        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.get_event_by_id = AsyncMock(return_value=None)

        with patch("audit_service.domain.services.AuditEventRepository", return_value=mock_repo):
            svc = AuditService(mock_session)
            with pytest.raises(AuditEventNotFoundError):
                await svc.get_event(uuid4())


class TestMetaAuditEmission:
    @pytest.mark.asyncio
    async def test_query_emits_meta_audit_task(self) -> None:
        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.query_events = AsyncMock(return_value=([], 0))
        mock_repo.get_last_event_hash = AsyncMock(return_value=None)
        mock_repo.write_event = AsyncMock(return_value=MagicMock())

        tasks_created: list[str] = []

        def _mock_create_task(coro: object, **kwargs: object) -> MagicMock:
            tasks_created.append("meta_task")
            task = MagicMock()
            task.__await__ = lambda self: iter([])
            return task

        with patch("audit_service.domain.services.AuditEventRepository", return_value=mock_repo):
            with patch("asyncio.create_task", side_effect=_mock_create_task):
                svc = AuditService(mock_session)
                await svc.query_events(
                    requesting_actor_id=uuid4(),
                    requesting_actor_type="user",
                    correlation_id=uuid4(),
                )

        assert len(tasks_created) == 1
