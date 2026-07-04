"""SHA-256 hash chain for audit event immutability (ENG-SPEC-005-04 §8.2).

Canonical string format:
    event_id | event_type | actor_id | action | outcome | timestamp_utc.isoformat()
    | prev_event_hash_or_GENESIS

All fields used in canonical computation are immutable once written.
timestamp_utc MUST be UTC-aware; isoformat() will include +00:00 offset.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

_SEPARATOR = "|"
_GENESIS_SENTINEL = "GENESIS"


def compute_event_hash(
    event_id: UUID,
    event_type: str,
    actor_id: UUID,
    action: str,
    outcome: str,
    timestamp_utc: datetime,
    prev_event_hash: str | None,
) -> str:
    canonical = _SEPARATOR.join(
        [
            str(event_id),
            event_type,
            str(actor_id),
            action,
            outcome,
            timestamp_utc.isoformat(),
            prev_event_hash if prev_event_hash is not None else _GENESIS_SENTINEL,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_single_link(
    event_id: UUID,
    event_type: str,
    actor_id: UUID,
    action: str,
    outcome: str,
    timestamp_utc: datetime,
    prev_event_hash: str | None,
    stored_hash: str,
) -> bool:
    """Return True iff stored_hash matches the computed hash for this event."""
    computed = compute_event_hash(
        event_id, event_type, actor_id, action, outcome, timestamp_utc, prev_event_hash
    )
    return computed == stored_hash
