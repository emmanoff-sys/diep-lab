"""Unit tests: SHA-256 hash chain (ENG-SPEC-005-04 §26.1 / §8.2)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from audit_service.core.hash_chain import compute_event_hash, verify_single_link


_TS = datetime(2026, 7, 4, 10, 0, 0, tzinfo=UTC)
_ACTOR = UUID("550e8400-e29b-41d4-a716-446655440000")
_EVENT = uuid4()


def _hash_fields(
    event_id: UUID,
    event_type: str,
    actor_id: UUID,
    action: str,
    outcome: str,
    timestamp_utc: datetime,
    prev: str | None,
) -> str:
    canonical = "|".join([
        str(event_id),
        event_type,
        str(actor_id),
        action,
        outcome,
        timestamp_utc.isoformat(),
        prev if prev is not None else "GENESIS",
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TestComputeEventHash:
    def test_genesis_event_uses_sentinel(self) -> None:
        h = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        expected = _hash_fields(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        assert h == expected

    def test_chained_event_includes_prev_hash(self) -> None:
        first_hash = compute_event_hash(
            _EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None
        )
        event2 = uuid4()
        ts2 = datetime(2026, 7, 4, 10, 1, 0, tzinfo=UTC)
        h2 = compute_event_hash(event2, "auth.token.refreshed", _ACTOR, "token.refresh",
                                "success", ts2, first_hash)
        expected = _hash_fields(event2, "auth.token.refreshed", _ACTOR, "token.refresh",
                                "success", ts2, first_hash)
        assert h2 == expected

    def test_hash_changes_when_outcome_mutated(self) -> None:
        h1 = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        h2 = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "failure", _TS, None)
        assert h1 != h2

    def test_hash_changes_when_event_type_mutated(self) -> None:
        h1 = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        h2 = compute_event_hash(_EVENT, "auth.login.failure", _ACTOR, "login", "success", _TS, None)
        assert h1 != h2

    def test_hash_changes_when_timestamp_mutated(self) -> None:
        ts2 = datetime(2026, 7, 4, 10, 0, 1, tzinfo=UTC)
        h1 = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        h2 = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", ts2, None)
        assert h1 != h2

    def test_three_event_chain_continuity(self) -> None:
        e1, e2, e3 = uuid4(), uuid4(), uuid4()
        ts1 = datetime(2026, 7, 4, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 7, 4, 10, 1, 0, tzinfo=UTC)
        ts3 = datetime(2026, 7, 4, 10, 2, 0, tzinfo=UTC)

        h1 = compute_event_hash(e1, "auth.login.success", _ACTOR, "login", "success", ts1, None)
        h2 = compute_event_hash(e2, "auth.token.refreshed", _ACTOR, "token.refresh",
                                "success", ts2, h1)
        h3 = compute_event_hash(e3, "auth.token.revoked", _ACTOR, "token.revoke",
                                "success", ts3, h2)

        # Verify each link
        assert verify_single_link(e1, "auth.login.success", _ACTOR, "login", "success", ts1, None, h1)
        assert verify_single_link(e2, "auth.token.refreshed", _ACTOR, "token.refresh",
                                  "success", ts2, h1, h2)
        assert verify_single_link(e3, "auth.token.revoked", _ACTOR, "token.revoke",
                                  "success", ts3, h2, h3)


class TestVerifySingleLink:
    def test_valid_link_returns_true(self) -> None:
        h = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        assert verify_single_link(
            _EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None, h
        )

    def test_tampered_hash_returns_false(self) -> None:
        assert not verify_single_link(
            _EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None, "deadbeef"
        )

    def test_broken_chain_detected_on_prev_hash_change(self) -> None:
        h = compute_event_hash(_EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, None)
        # Tamper: stored hash was computed with GENESIS but we pass a different prev
        assert not verify_single_link(
            _EVENT, "auth.login.success", _ACTOR, "login", "success", _TS, "some_prev_hash", h
        )
