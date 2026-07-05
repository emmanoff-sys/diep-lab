"""Unit tests: Pydantic schemas (ENG-SPEC-005-04 §26.1 / §11.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from audit_service.api.v1.schemas.audit_event import AuditEventCreate, AuditEventResponse
from pydantic import ValidationError


def _base_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
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
    }
    payload.update(overrides)
    return payload


class TestAuditEventCreate:
    def test_valid_payload_parses(self) -> None:
        obj = AuditEventCreate(**_base_payload())  # type: ignore[arg-type]
        assert obj.event_type == "auth.login.success"

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(ValidationError, match="UTC-aware"):
            AuditEventCreate(**_base_payload(timestamp_utc=datetime(2026, 7, 4, 10, 0, 0)))  # type: ignore[arg-type]

    def test_metadata_size_limit_4096(self) -> None:
        big_meta = {"key": "x" * 5000}
        with pytest.raises(ValidationError, match="4096"):
            AuditEventCreate(**_base_payload(metadata=big_meta))  # type: ignore[arg-type]

    def test_metadata_within_limit_accepted(self) -> None:
        small_meta = {"key": "value"}
        obj = AuditEventCreate(**_base_payload(metadata=small_meta))  # type: ignore[arg-type]
        assert obj.metadata == small_meta

    def test_outcome_invalid_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditEventCreate(**_base_payload(outcome="unknown"))  # type: ignore[arg-type]

    def test_actor_type_invalid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditEventCreate(**_base_payload(actor_type="robot"))  # type: ignore[arg-type]

    def test_event_type_max_length(self) -> None:
        with pytest.raises(ValidationError):
            AuditEventCreate(**_base_payload(event_type="a" * 101))  # type: ignore[arg-type]

    def test_missing_required_field(self) -> None:
        payload = _base_payload()
        del payload["event_id"]
        with pytest.raises(ValidationError):
            AuditEventCreate(**payload)  # type: ignore[arg-type]

    def test_pii_fields_optional(self) -> None:
        obj = AuditEventCreate(
            **_base_payload(  # type: ignore[arg-type]
                actor_username="alice",
                actor_ip_address="192.168.1.1",
                actor_user_agent="Mozilla/5.0",
            )
        )
        assert obj.actor_username == "alice"
        assert obj.actor_ip_address == "192.168.1.1"

    def test_schema_version_defaults_to_1(self) -> None:
        obj = AuditEventCreate(**_base_payload())  # type: ignore[arg-type]
        assert obj.schema_version == 1

    def test_utc_offset_preserved(self) -> None:
        ts = datetime(2026, 7, 4, 10, 0, 0, tzinfo=UTC)
        obj = AuditEventCreate(**_base_payload(timestamp_utc=ts))  # type: ignore[arg-type]
        assert obj.timestamp_utc.tzinfo is not None


class TestAuditEventResponse:
    """AuditEventResponse must include PII fields for admin:audit forensic use (C-AR052-04)."""

    def _mock_event(self, **overrides: object) -> MagicMock:
        m = MagicMock()
        m.id = uuid4()
        m.event_id = uuid4()
        m.event_type = "auth.login.success"
        m.actor_type = "user"
        m.actor_id = uuid4()
        m.actor_username = None
        m.actor_ip_address = None
        m.actor_user_agent = None
        m.action = "login"
        m.resource_type = "session"
        m.resource_id = None
        m.outcome = "success"
        m.outcome_reason = None
        m.correlation_id = uuid4()
        m.session_id = None
        m.service_name = "identity-service"
        m.service_version = None
        m.prev_event_hash = None
        m.event_hash = "a" * 64
        m.metadata = None
        m.timestamp_utc = datetime.now(UTC)
        m.ingested_at_utc = datetime.now(UTC)
        m.schema_version = 1
        for k, v in overrides.items():
            setattr(m, k, v)
        return m

    def test_pii_fields_present_in_response_schema(self) -> None:
        """PII fields are included in AuditEventResponse (C-AR052-04 — not accidental omission)."""
        event = self._mock_event(
            actor_username="alice",
            actor_ip_address="198.51.100.42",
            actor_user_agent="Mozilla/5.0",
        )
        resp = AuditEventResponse.model_validate(event)
        assert resp.actor_username == "alice"
        assert resp.actor_ip_address == "198.51.100.42"
        assert resp.actor_user_agent == "Mozilla/5.0"

    def test_pii_fields_null_when_not_provided(self) -> None:
        event = self._mock_event()
        resp = AuditEventResponse.model_validate(event)
        assert resp.actor_username is None
        assert resp.actor_ip_address is None
        assert resp.actor_user_agent is None
