"""reos-common — DAEP / RE-OS common backend utilities.

Authority: WP-002-07 | LLD v2.0 §2.1.1 (tenant-scoping + soft-delete
pattern) | DRDP v1.0 §21 (cursor-pagination convention).

Usage::

    from reos_common import Page, PageParams, tenant_scoped, utc_now
"""

from reos_common.datetime_utils import to_iso8601, utc_now
from reos_common.pagination import Page, PageParams, decode_cursor, encode_cursor
from reos_common.tenant import tenant_scoped

__all__ = [
    "Page",
    "PageParams",
    "decode_cursor",
    "encode_cursor",
    "tenant_scoped",
    "to_iso8601",
    "utc_now",
]
