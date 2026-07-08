"""Deterministic operational state update processing."""

from __future__ import annotations

from .models import OperationalStateError, StateUpdate, UpdateResult
from .repository import InMemoryOperationalStateRepository
from .validation import OperationalStateValidator


class StateUpdateEngine:
    def __init__(
        self,
        repository: InMemoryOperationalStateRepository,
        validator: OperationalStateValidator,
    ) -> None:
        self.repository = repository
        self.validator = validator

    def process(self, update: StateUpdate) -> UpdateResult:
        report = self.validator.validate_update(update)
        if not report.is_valid:
            report.raise_if_invalid()
        return self.repository.apply(update)

    def process_many(self, updates: tuple[StateUpdate, ...]) -> tuple[UpdateResult, ...]:
        ordered = tuple(sorted(updates, key=lambda item: (item.sequence, item.update_id)))
        results: list[UpdateResult] = []
        for update in ordered:
            try:
                results.append(self.process(update))
            except OperationalStateError:
                raise
        return tuple(results)
