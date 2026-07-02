"""Structurally enforced tenant scoping — the LLD's "ALWAYS tenant-scoped" rule.

Authority: WP-002-07 | LLD v2.0 §2.1.1 (worked example:
``.where(Customer.tenant_id == current_tenant_id)  # ALWAYS tenant-scoped``
plus the ``is_deleted`` soft-delete filter).

This helper is the primary data-isolation control at the query layer
(WP-002-07 §25, §39): a missed ``tenant_id`` filter is a data-leak bug, so
the rule is enforced by code, not memory.

Required schema convention (Release 2+ — WP-002-07 §22, §35): every
multi-tenant table has ``tenant_id`` and ``is_deleted`` columns.
"""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select

from reos_exceptions import AuthorizationError
from reos_logging import get_logger

__all__ = ["tenant_scoped"]

log = get_logger(__name__)

_T = TypeVar("_T", bound=tuple[Any, ...])


def tenant_scoped(query: Select[_T], tenant_id: UUID | None) -> Select[_T]:
    """Apply mandatory tenant and soft-delete filters to ``query``.

    Adds ``.where(Model.tenant_id == tenant_id).where(Model.is_deleted == False)``
    for the query's primary entity.

    :raises AuthorizationError: if ``tenant_id`` is ``None`` — a request
        without tenant context must never reach the database unscoped.
    :raises TypeError: if the query's entity lacks the required
        ``tenant_id``/``is_deleted`` columns (schema convention violation).
    """
    if tenant_id is None:
        log.warning("tenant.missing_context", query=str(query.column_descriptions))
        raise AuthorizationError(metadata={"reason": "missing_tenant_context"})

    descriptions = query.column_descriptions
    if not descriptions:
        raise TypeError("tenant_scoped() requires a SELECT over a mapped entity.")
    entity = descriptions[0].get("entity")
    if entity is None:
        raise TypeError("tenant_scoped() requires a SELECT over a mapped entity.")

    for required in ("tenant_id", "is_deleted"):
        if not hasattr(entity, required):
            raise TypeError(
                f"{entity.__name__} has no '{required}' column — every "
                "multi-tenant model must define tenant_id and is_deleted "
                "(WP-002-07 schema convention)."
            )

    return query.where(entity.tenant_id == tenant_id).where(
        entity.is_deleted == False  # noqa: E712 — SQLAlchemy needs the comparison, not `is False`
    )
