from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DomainEvent", "ExampleCreated"]


@dataclass(frozen=True)
class DomainEvent:
    """Base for all domain events emitted by this service."""

    aggregate_id: int
    event_type: str


@dataclass(frozen=True)
class ExampleCreated(DomainEvent):
    name: str
