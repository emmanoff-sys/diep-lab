"""OA-093 — AMI adapter replay and test harness datasets.

Canonical AMI datasets for deterministic connector testing. The
meter-identity map and canonical messages align with the two-feeder
topology (WP-011-01 OA-073 §5) so that AMI events can be ingested
alongside the SCADA canonical dataset without topology conflicts.
"""

from __future__ import annotations

from typing import Any

from .translation import AMIMessage

# --- Canonical AMI meter identity map -----------------------------------
# Maps AMI meter IDs → (canonical asset_id, "node").
# Load nodes c (40 customers) and e (10 customers) in the two-feeder
# topology are the metered network attachment points.

AMI_CANONICAL_METER_MAP: dict[str, tuple[str, str]] = {
    "AMI:METER-C-001": ("c", "node"),
    "AMI:METER-C-002": ("c", "node"),
    "AMI:METER-E-001": ("e", "node"),
    "AMI:METER-E-002": ("e", "node"),
}

# --- Canonical AMI event dataset ----------------------------------------

AMI_LAST_GASP_EVENT = AMIMessage(
    message_id="AMI:METER-C-001:LASTGASP:001",
    meter_id="AMI:METER-C-001",
    message_type="last_gasp",
    observed_at="2026-07-10T06:00:00Z",
    sequence=1,
    raw_payload={"available": False, "voltage_v": 0.0, "reason": "power_loss"},
)

AMI_RESTORATION_EVENT = AMIMessage(
    message_id="AMI:METER-C-001:RESTORE:001",
    meter_id="AMI:METER-C-001",
    message_type="restoration",
    observed_at="2026-07-10T06:30:00Z",
    sequence=2,
    raw_payload={"available": True, "voltage_v": 230.0, "reason": "power_restored"},
)

AMI_METER_READING_EVENT = AMIMessage(
    message_id="AMI:METER-E-001:READ:001",
    meter_id="AMI:METER-E-001",
    message_type="meter_reading",
    observed_at="2026-07-10T06:15:00Z",
    sequence=1,
    raw_payload={"energized": True, "kwh": 123.4, "kw": 2.1},
)

AMI_TAMPER_EVENT = AMIMessage(
    message_id="AMI:METER-E-002:TAMPER:001",
    meter_id="AMI:METER-E-002",
    message_type="tamper",
    observed_at="2026-07-10T06:45:00Z",
    sequence=2,
    raw_payload={"available": True, "tamper_type": "magnetic"},
)

# Ordered batch: last_gasp → reading → restoration → tamper
AMI_CANONICAL_BATCH: tuple[AMIMessage, ...] = (
    AMI_LAST_GASP_EVENT,
    AMI_METER_READING_EVENT,
    AMI_RESTORATION_EVENT,
    AMI_TAMPER_EVENT,
)


class AmiStub:
    """Deterministic AMI event source for connector testing.

    Emits raw AMI event dicts from a fixed sequence; exhausts cleanly
    and resets deterministically. Implements the OA-073 §4 stub spec
    for the AMI protocol.
    """

    def __init__(self, events: tuple[dict[str, Any], ...]) -> None:
        self._events = events
        self._index = 0

    @classmethod
    def from_messages(cls, messages: tuple[AMIMessage, ...]) -> AmiStub:
        """Build a stub from canonical AMIMessage objects."""
        return cls(
            tuple(
                {
                    "message_id": m.message_id,
                    "meter_id": m.meter_id,
                    "message_type": m.message_type,
                    "observed_at": m.observed_at,
                    "sequence": m.sequence,
                    "raw_payload": dict(m.raw_payload),
                }
                for m in messages
            )
        )

    def next_event(self) -> dict[str, Any] | None:
        if self._index >= len(self._events):
            return None
        event = self._events[self._index]
        self._index += 1
        return event

    def reset(self) -> None:
        self._index = 0

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._events)

    @property
    def remaining(self) -> int:
        return max(0, len(self._events) - self._index)
