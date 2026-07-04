"""Unit tests for cursor pagination — WP-002-07 §29, §33.

Round-trips correctly (page 1 → cursor → page 2, no duplicates/gaps),
respects limits, rejects malformed cursors.
"""

from __future__ import annotations

import pytest
from reos_common import Page, PageParams, decode_cursor, encode_cursor
from reos_common.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from reos_exceptions import ValidationError


class TestCursorCodec:
    def test_round_trip(self) -> None:
        for offset in (0, 1, 50, 12345):
            assert decode_cursor(encode_cursor(offset)) == offset

    def test_cursor_is_opaque_not_plain_text(self) -> None:
        assert "50" not in encode_cursor(50)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "not-base64!!",
            "b2Zmc2V0Oi01",  # offset:-5 — negative
            "aGVsbG8=",  # hello — no prefix
            "b2Zmc2V0OmFiYw==",  # offset:abc — non-integer
        ],
    )
    def test_malformed_cursor_raises_validation_error(self, bad: str) -> None:
        with pytest.raises(ValidationError) as excinfo:
            decode_cursor(bad)
        assert excinfo.value.http_status == 422

    def test_negative_offset_rejected_at_encode(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            encode_cursor(-1)


class TestPageParams:
    def test_defaults(self) -> None:
        params = PageParams()
        assert params.limit == DEFAULT_PAGE_LIMIT
        assert params.offset == 0

    def test_offset_from_cursor(self) -> None:
        params = PageParams(cursor=encode_cursor(100))
        assert params.offset == 100

    def test_limit_clamped_to_max(self) -> None:
        assert PageParams(limit=10_000).limit == MAX_PAGE_LIMIT

    def test_zero_limit_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PageParams(limit=0)


class TestPageRoundTrip:
    def test_two_page_walk_no_duplicates_no_gaps(self) -> None:
        dataset = list(range(7))
        params1 = PageParams(limit=4)
        page1: Page[int] = Page.build(
            dataset[params1.offset : params1.offset + params1.limit + 1], params1
        )
        assert page1.items == [0, 1, 2, 3]
        assert page1.next_cursor is not None

        params2 = PageParams(cursor=page1.next_cursor, limit=4)
        page2: Page[int] = Page.build(
            dataset[params2.offset : params2.offset + params2.limit + 1], params2
        )
        assert page2.items == [4, 5, 6]
        assert page2.next_cursor is None

        walked = page1.items + page2.items
        assert walked == dataset  # no duplicates, no gaps

    def test_exact_page_boundary_has_no_next(self) -> None:
        params = PageParams(limit=4)
        page: Page[int] = Page.build([0, 1, 2, 3], params)
        assert page.items == [0, 1, 2, 3]
        assert page.next_cursor is None

    def test_empty_result(self) -> None:
        page: Page[int] = Page.build([], PageParams())
        assert page.items == []
        assert page.next_cursor is None
