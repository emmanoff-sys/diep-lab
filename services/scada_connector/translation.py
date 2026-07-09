"""OA-076 — canonical event translation.

Deterministic translation of raw SCADA messages into canonical
OperationalEvent objects (WP-011-01 OA-070 contract v1.0). Every field
mapping is explicit; no default values are assumed for mandatory fields.

No business logic: the translator does not interpret what a switch-open
event means for the network — that is WP-009's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.adms_operational_state import OperationalEvent

from .framework import SCADAConnectorError

# Mapping from SCADA message_type to canonical event_type
_EVENT_TYPE_MAP: dict[str, str] = {
    "status_change": "breaker_operation",
    "alarm": "alarm",
    "measurement": "telemetry",
}

# Required payload keys per canonical event_type
_REQUIRED_PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    "breaker_operation": ("status", "available"),
    "alarm": ("available",),
    "telemetry": ("energized",),
}


@dataclass(frozen=True)
class SCADAMessage:
    """A raw SCADA message before normalisation."""

    message_id: str
    external_asset_id: str
    message_type: str
    observed_at: str
    sequence: int
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class TranslationResult:
    message_id: str
    success: bool
    event: OperationalEvent | None
    rejection_reason: str | None


class AssetIdentityMap:
    """Maps SCADA-side external asset IDs to canonical asset_id values.

    Validated at construction time against a known set of asset IDs;
    raises `SCADAConnectorError` on startup if any mapping target is
    not in the topology (fail-fast per OA-069 §8).
    """

    def __init__(
        self,
        mapping: dict[str, tuple[str, str]],
        known_asset_ids: frozenset[str] | None = None,
    ) -> None:
        """mapping: {external_id: (asset_id, asset_kind)}"""
        self._map = dict(mapping)
        if known_asset_ids is not None:
            unknown = {
                asset_id for asset_id, _ in self._map.values() if asset_id not in known_asset_ids
            }
            if unknown:
                raise SCADAConnectorError(
                    "asset identity map references unknown asset IDs: " + ", ".join(sorted(unknown))
                )

    def resolve(self, external_id: str) -> tuple[str, str]:
        """Return (asset_id, asset_kind) or raise SCADAConnectorError."""
        result = self._map.get(external_id)
        if result is None:
            raise SCADAConnectorError(f"external asset ID not in identity map: {external_id}")
        return result

    @property
    def mapped_external_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._map))


class SCADAEventTranslator:
    """Translates SCADAMessage → TranslationResult (OperationalEvent).

    Deterministic: given the same message and identity map, always
    produces the same result. No wall clock, no randomness.
    """

    def __init__(self, identity_map: AssetIdentityMap, actor: str) -> None:
        self._map = identity_map
        self._actor = actor

    def translate(self, message: SCADAMessage) -> TranslationResult:
        # Step 1: resolve asset identity
        try:
            asset_id, asset_kind = self._map.resolve(message.external_asset_id)
        except SCADAConnectorError as error:
            return TranslationResult(
                message_id=message.message_id,
                success=False,
                event=None,
                rejection_reason=str(error),
            )

        # Step 2: map event type
        event_type = _EVENT_TYPE_MAP.get(message.message_type)
        if event_type is None:
            return TranslationResult(
                message_id=message.message_id,
                success=False,
                event=None,
                rejection_reason=(
                    f"unknown message_type '{message.message_type}'; "
                    f"allowed: {', '.join(sorted(_EVENT_TYPE_MAP))}"
                ),
            )

        # Step 3: validate and extract canonical payload
        required = _REQUIRED_PAYLOAD_KEYS[event_type]
        missing = [key for key in required if key not in message.raw_payload]
        if missing:
            return TranslationResult(
                message_id=message.message_id,
                success=False,
                event=None,
                rejection_reason=(
                    f"payload missing required keys for {event_type}: " + ", ".join(missing)
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
        return TranslationResult(
            message_id=message.message_id,
            success=True,
            event=event,
            rejection_reason=None,
        )

    def translate_many(self, messages: tuple[SCADAMessage, ...]) -> tuple[TranslationResult, ...]:
        return tuple(self.translate(msg) for msg in messages)
