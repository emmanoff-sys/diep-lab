from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reos_common import Page, PageParams, tenant_scoped

from service_name.domain.models import ExampleModel

__all__ = ["ExampleRepository"]


class ExampleRepository:
    """Demonstrates the mandatory reos-common query patterns (WP-002-07).

    NOTE (template only): ExampleModel has no tenant_id/is_deleted columns —
    ``list_for_tenant`` is illustrative. Real multi-tenant models MUST define
    both columns (reos-common schema convention) before using tenant_scoped.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: int) -> ExampleModel | None:
        return await self._session.get(ExampleModel, entity_id)

    async def list_for_tenant(
        self, tenant_id: UUID, params: PageParams
    ) -> Page[ExampleModel]:
        query = (
            tenant_scoped(select(ExampleModel), tenant_id)  # ALWAYS tenant-scoped
            .offset(params.offset)
            .limit(params.limit + 1)  # fetch one extra row to detect next page
        )
        rows = (await self._session.scalars(query)).all()
        return Page.build(list(rows), params)
