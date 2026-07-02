"""Cursor-based pagination helpers.

Authority: WP-002-07 | DRDP v1.0 §21 API Mapping (cursor-pagination
convention, e.g. ``GET /users?tenant_id&cursor&status``).

Cursor format: opaque URL-safe base64 of the next offset. Treat cursors as
opaque tokens on the wire — the encoding is an implementation detail and may
change; clients must never construct or parse them.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from reos_exceptions import ValidationError

__all__ = ["Page", "PageParams", "decode_cursor", "encode_cursor"]

_T = TypeVar("_T")

_CURSOR_PREFIX = "offset:"
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


def encode_cursor(offset: int) -> str:
    """Encode ``offset`` as an opaque URL-safe cursor token."""
    if offset < 0:
        raise ValueError("offset must be non-negative")
    raw = f"{_CURSOR_PREFIX}{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> int:
    """Decode a cursor token back to its offset.

    :raises ValidationError: (HTTP 422) for malformed or tampered cursors —
        client input is never trusted.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValidationError("Invalid pagination cursor.") from exc
    if not raw.startswith(_CURSOR_PREFIX):
        raise ValidationError("Invalid pagination cursor.")
    try:
        offset = int(raw.removeprefix(_CURSOR_PREFIX))
    except ValueError as exc:
        raise ValidationError("Invalid pagination cursor.") from exc
    if offset < 0:
        raise ValidationError("Invalid pagination cursor.")
    return offset


@dataclass(frozen=True)
class PageParams:
    """Incoming pagination parameters (``?cursor=&limit=``).

    ``limit`` is clamped to ``MAX_PAGE_LIMIT`` — a client cannot request an
    unbounded page.
    """

    cursor: str | None = None
    limit: int = DEFAULT_PAGE_LIMIT

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValidationError("Page limit must be at least 1.")
        if self.limit > MAX_PAGE_LIMIT:
            object.__setattr__(self, "limit", MAX_PAGE_LIMIT)

    @property
    def offset(self) -> int:
        """Offset decoded from the cursor (0 for the first page)."""
        return 0 if self.cursor is None else decode_cursor(self.cursor)


@dataclass(frozen=True)
class Page(Generic[_T]):
    """One page of results plus the cursor for the next page (if any)."""

    items: list[_T] = field(default_factory=list)
    next_cursor: str | None = None

    @classmethod
    def build(cls, items: list[_T], params: PageParams) -> Page[_T]:
        """Build a page from a query result fetched with ``limit + 1`` rows.

        Fetch ``params.limit + 1`` rows; if the extra row exists, there is a
        next page and it is trimmed off — no duplicates, no gaps.
        """
        has_next = len(items) > params.limit
        page_items = items[: params.limit]
        next_cursor = (
            encode_cursor(params.offset + params.limit) if has_next else None
        )
        return cls(items=page_items, next_cursor=next_cursor)
