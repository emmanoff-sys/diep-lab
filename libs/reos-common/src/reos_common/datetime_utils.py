"""UTC-safe date/time helpers — naive datetimes are a bug, not an option.

Authority: WP-002-07 §15.
"""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["to_iso8601", "utc_now"]


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime (never naive)."""
    return datetime.now(UTC)


def to_iso8601(dt: datetime) -> str:
    """Render an aware datetime as an ISO-8601 string in UTC.

    :raises ValueError: for naive datetimes — ambiguity is refused, not
        silently assumed to be UTC.
    """
    if dt.tzinfo is None:
        raise ValueError("Naive datetime rejected — attach a timezone (use utc_now()).")
    return dt.astimezone(UTC).isoformat()
