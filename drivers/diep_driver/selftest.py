"""Selftest for the SDK store-and-forward (Phase 9A) — no broker required.

Drives Runner._publish_telemetry with a fake transport whose `connected` flag we
toggle, and asserts that readings are buffered while offline and replayed in order
(oldest first) on reconnect.

Run from drivers/:
    python -m diep_driver.selftest
"""
from __future__ import annotations

import sys

from diep_driver import BaseDriver, CommandResult, Runner


class _FakeTransport:
    def __init__(self):
        self.connected = False
        self.published: list[str] = []

    def publish(self, topic, payload, qos=0):
        self.published.append(payload)


class _FakeDriver(BaseDriver):
    domain = "test"

    def connect(self):  # pragma: no cover
        pass

    def read_telemetry(self):  # pragma: no cover
        return {}

    def execute_command(self, command_type, params):  # pragma: no cover
        return CommandResult("ACKED")


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not cond:
            failures.append(name)

    t = _FakeTransport()
    runner = Runner(_FakeDriver("DEV1"), transport=t, buffer_size=100)

    # Offline: 5 readings buffered, nothing published.
    t.connected = False
    for i in range(5):
        runner._publish_telemetry(f"reading-{i}")
    check("nothing published while offline", t.published == [], f"{t.published}")
    check("5 readings buffered", len(runner._buffer) == 5, f"{len(runner._buffer)}")

    # Reconnect: next publish flushes the buffer (in order) then sends the current one.
    t.connected = True
    runner._publish_telemetry("reading-5")
    expected = [f"reading-{i}" for i in range(6)]
    check("buffer replayed in order + current sent", t.published == expected, f"{t.published}")
    check("buffer drained", len(runner._buffer) == 0)

    # Steady state: subsequent readings go straight out.
    runner._publish_telemetry("reading-6")
    check("steady-state direct publish", t.published[-1] == "reading-6")

    # Bounded buffer: never grows past maxlen (drops oldest).
    t.connected = False
    small = Runner(_FakeDriver("DEV2"), transport=_FakeTransport(), buffer_size=10)
    small.transport.connected = False
    for i in range(25):
        small._publish_telemetry(f"r{i}")
    check("bounded buffer caps at maxlen", len(small._buffer) == 10, f"{len(small._buffer)}")
    check("oldest dropped (ring buffer)", small._buffer[0] == "r15", f"{small._buffer[0]}")

    print()
    if failures:
        print(f"SELFTEST FAILED: {failures}")
        return 1
    print("SELFTEST PASSED — store-and-forward buffers + replays correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
