"""OA-079 / OA-073 — deterministic external-system stubs.

Stubs produce the same output given the same input configuration on
every test run: no randomness, no wall clock. Implements the stub
specifications from WP-011-01 OA-073 §4.
"""

from __future__ import annotations

from typing import Any


class ScadaStub:
    """Deterministic SCADA telemetry source for connector testing.

    Emits raw SCADA message dicts from a fixed sequence; exhausts
    cleanly and resets deterministically.
    """

    def __init__(self, messages: tuple[dict[str, Any], ...]) -> None:
        self._messages = messages
        self._index = 0

    def next_message(self) -> dict[str, Any] | None:
        if self._index >= len(self._messages):
            return None
        msg = self._messages[self._index]
        self._index += 1
        return msg

    def reset(self) -> None:
        self._index = 0

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._messages)

    @property
    def remaining(self) -> int:
        return max(0, len(self._messages) - self._index)


class GisStub:
    """Deterministic GIS model source for adapter testing."""

    def __init__(self, mapped_topology: Any) -> None:
        self._topology = mapped_topology

    def fetch_model(self) -> Any:
        return self._topology


class OmsStub:
    """Deterministic OMS historical event source."""

    def __init__(self, events: tuple[Any, ...]) -> None:
        self._events = events

    def fetch_history(self) -> tuple[Any, ...]:
        return self._events
