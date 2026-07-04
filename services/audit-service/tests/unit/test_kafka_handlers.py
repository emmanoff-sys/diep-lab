"""Unit tests: Kafka message parsing and DLQ routing (ENG-SPEC-005-04 §26.1 / §10)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from audit_service.core.kafka import _parse_message, _route_to_dlq
from audit_service.domain.events import user_registered_to_audit


class TestParseMessage:
    def test_iam_audit_events_message_parsed(self) -> None:
        msg = {
            "event_id": str(uuid4()),
            "event_type": "auth.login.success",
            "actor_type": "user",
            "actor_id": str(uuid4()),
            "action": "login",
            "resource_type": "session",
            "outcome": "success",
            "correlation_id": str(uuid4()),
            "service_name": "identity-service",
            "timestamp_utc": "2026-07-04T10:00:00+00:00",
        }
        result = _parse_message("iam.audit.events", msg)
        assert result["event_type"] == "auth.login.success"
        assert result["timestamp_utc"].tzinfo is not None  # type: ignore[union-attr]

    def test_user_registered_message_converted(self) -> None:
        msg = {
            "event_type": "user.registered",
            "user_id": str(uuid4()),
            "email": "user@example.com",
            "timestamp": "2026-07-04T10:00:00+00:00",
            "correlation_id": str(uuid4()),
        }
        result = _parse_message("user.registered", msg)
        assert result["event_type"] == "user.registered"
        assert result["action"] == "user.register"
        assert result["resource_type"] == "user"

    def test_iam_message_missing_required_field_raises(self) -> None:
        msg = {
            "event_id": str(uuid4()),
            # missing event_type, actor_type, etc.
        }
        with pytest.raises(ValueError, match="Missing required fields"):
            _parse_message("iam.audit.events", msg)

    def test_naive_timestamp_coerced_to_utc(self) -> None:
        msg = {
            "event_id": str(uuid4()),
            "event_type": "auth.login.success",
            "actor_type": "user",
            "actor_id": str(uuid4()),
            "action": "login",
            "resource_type": "session",
            "outcome": "success",
            "correlation_id": str(uuid4()),
            "service_name": "identity-service",
            "timestamp_utc": "2026-07-04T10:00:00",  # naive
        }
        result = _parse_message("iam.audit.events", msg)
        assert result["timestamp_utc"].tzinfo is not None  # type: ignore[union-attr]


class TestUserRegisteredConversion:
    def test_missing_user_id_raises(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            user_registered_to_audit(
                {"email": "x@example.com", "timestamp": "2026-07-04T10:00:00+00:00"}
            )

    def test_outcome_is_success(self) -> None:
        result = user_registered_to_audit(
            {
                "event_type": "user.registered",
                "user_id": str(uuid4()),
                "email": "u@example.com",
                "timestamp": "2026-07-04T10:00:00+00:00",
                "correlation_id": str(uuid4()),
            }
        )
        assert result["outcome"] == "success"


class TestDLQRouting:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_producer(self) -> None:
        import audit_service.core.kafka as kafka_mod

        original = kafka_mod._dlq_producer
        kafka_mod._dlq_producer = None
        result = await _route_to_dlq("iam.audit.events", {}, "test error")
        assert result is False
        kafka_mod._dlq_producer = original

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_publish(self) -> None:
        import audit_service.core.kafka as kafka_mod

        mock_producer = MagicMock()
        mock_producer.send_and_wait = AsyncMock()
        kafka_mod._dlq_producer = mock_producer  # type: ignore[assignment]
        result = await _route_to_dlq("iam.audit.events", {"key": "val"}, "db error")
        assert result is True
        kafka_mod._dlq_producer = None
