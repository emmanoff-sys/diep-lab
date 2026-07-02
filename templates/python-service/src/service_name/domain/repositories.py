from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from service_name.domain.models import ExampleModel

__all__ = ["ExampleRepository"]


class ExampleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: int) -> ExampleModel | None:
        return await self._session.get(ExampleModel, entity_id)
