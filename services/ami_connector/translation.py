"""OA-090 — canonical metering translation.

Deterministic translation of raw AMI messages into canonical
OperationalEvent objects (WP-011-01 OA-070 contract v1.0). Every field
mapping is explicit; no default values are assumed for mandatory fields.

No business logic: the translator does not interpret what a last-gasp
event means for the network — that is WP-009's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.adms_operational_state import OperationalEvent

from .framework import AMIConnectorError

# Mapping from AMI message_type to canonical event_type
_AMI_EVENT_TYPE_MAP: dict[str, str] = {
    "last_gasp": "alarm",
    "restoration": "alarm",
    "tamper": "alarm",
    "meter_reading": "telemetry",
    "power_quality": "telemetry",
    "diagnostic": "telemetry",
}

# Required payload keys per canonical event_type (subset used by AMI)
_REQUIRED_PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    "alarm": ("available",),
    "telemetry": ("energized",),
}


@dataclass(frozen=True)
class AMIMessage:
    """A raw AMI event before normalisation."""

    message_id: str
    meter_id: str
    message_type: str
    observed_at: str
    sequence: int
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class AMIEventRejection:
    message_id: str
    meter_id: str
    reason: str


@dataclass(frozen=True)
class AMITranslationResult:
    message_id: str
    success: bool
    event: OperationalEvent | None
    rejection: AMIEventRejection | None


class AMIEventTranslator:
    """Translates AMIMessage → AMITranslationResult (OperationalEvent).

    Deterministic: given the same message and identity map, always
    produces the same result. No wall clock, no randomness.
    """

    def __init__(self, identity_map: Any, actor: str) -> None:
        self._map = identity_map
        self._actor = actor

    def translate(self, message: AMIMessage) -> AMITranslationResult:
        # Step 1: resolve meter identity
        try:
            asset_id, asset_kind = self._map.resolve(message.meter_id)
        except AMIConnectorError as error:
            return AMITranslationResult(
                message_id=message.message_id,
                success=False,
                event=None,
                rejection=AMIEventRejection(
                    message_id=message.message_id,
                    meter_id=message.meter_id,
                    reason=str(error),
                ),
            )

        # Step 2: map AMI event type to canonical event type
        event_type = _AMI_EVENT_TYPE_MAP.get(message.message_type)
        if event_type is None:
            return AMITranslationResult(
                message_id=message.message_id,
                success=False,
                event=None,
                rejection=AMIEventRejection(
                    message_id=message.message_id,
                    meter_id=message.meter_id,
                    reason=(
                        f"unknown message_type '{message.message_type}'; "
                        f"allowed: {', '.join(sorted(_AMI_EVENT_TYPE_MAP))}"
                    ),
                ),
            )

        # Step 3: validate and extract canonical payload
        required = _REQUIRED_PAYLOAD_KEYS[event_type]
        missing = [key for key in required if key not in message.raw_payload]
        if missing:
            return AMITranslationResult(
                message_id=message.message_id,
                success=False,
                event=None,
                rejection=AMIEventRejection(
                    message_id=message.message_id,
                    meter_id=message.meter_id,
                    reason=(
                        f"payload missing required keys for {event_type}: " + ", ".join(missing)
                    ),
                ),
            )
        payload = {key: message.raw_payload[key] for key in required}

        # Step 4: construct canonical contract
        event = OperationalEvent(
            event_id=f"{self._actor}:{message.message_id}",
            event_type=event_type,
            asset_id=asset_id,
            asset_kind=asset_kind,
            sequence=message.sequence,
            observed_at=message.observed_at,
            actor=self._actor,
            payload=payload,
        )
        return AMITranslationResult(
            message_id=message.message_id,
            success=True,
            event=event,
            rejection=None,
        )

    def translate_many(self, messages: tuple[AMIMessage, ...]) -> tuple[AMITranslationResult, ...]:
        return tuple(self.translate(msg) for msg in messages)
