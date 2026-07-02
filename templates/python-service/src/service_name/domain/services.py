from __future__ import annotations

from service_name.domain.models import ExampleModel
from service_name.domain.repositories import ExampleRepository

__all__ = ["ExampleService"]


class ExampleService:
    def __init__(self, repository: ExampleRepository) -> None:
        self._repository = repository

    async def get(self, entity_id: int) -> ExampleModel | None:
        return await self._repository.get_by_id(entity_id)
