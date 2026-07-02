from __future__ import annotations

from typing import Protocol, runtime_checkable

# PLACEHOLDER: Kafka producer/consumer interface scaffold.
# Replace with the shared messaging library from libs/ once WP-002-04 delivers it —
# do not wire real aiokafka clients here until domain events are defined in EPIC-002.

__all__ = ["EventProducer", "EventConsumer"]


@runtime_checkable
class EventProducer(Protocol):
    async def publish(self, topic: str, key: bytes, value: bytes) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class EventConsumer(Protocol):
    async def subscribe(self, topics: list[str]) -> None: ...

    async def close(self) -> None: ...
