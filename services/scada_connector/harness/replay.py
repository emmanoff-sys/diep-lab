"""OA-079 / OA-073 — session recorder and replayer.

Records raw SCADA messages from a live or stubbed session and replays
them deterministically. Implements OA-073 §6.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionRecorder:
    """Records raw SCADA message dicts for deterministic replay."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def record(self, message: dict[str, Any]) -> None:
        self._records.append(dict(message))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            "\n".join(json.dumps(record) for record in self._records),
            encoding="utf-8",
        )

    def messages(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._records)

    @property
    def count(self) -> int:
        return len(self._records)


class SessionReplayer:
    """Replays a recorded session against a stub or connector under test."""

    def __init__(self, path: str | Path) -> None:
        text = Path(path).read_text(encoding="utf-8").strip()
        self._messages: tuple[dict[str, Any], ...] = tuple(
            json.loads(line) for line in text.splitlines() if line.strip()
        )

    @classmethod
    def from_messages(cls, messages: tuple[dict[str, Any], ...]) -> SessionReplayer:
        """Create a replayer directly from in-memory messages (no file I/O)."""
        replayer = object.__new__(cls)
        replayer._messages = messages
        return replayer

    def replay(self, stub) -> tuple[dict[str, Any], ...]:
        """Push all recorded messages into the stub and return them."""
        results: list[dict[str, Any]] = []
        for message in self._messages:
            stub.record(message) if hasattr(stub, "record") else None
            results.append(message)
        return tuple(results)

    @property
    def messages(self) -> tuple[dict[str, Any], ...]:
        return self._messages

    @property
    def count(self) -> int:
        return len(self._messages)
