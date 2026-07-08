"""Operational event processing for network state changes."""

from __future__ import annotations

from .engine import StateUpdateEngine
from .models import EventProcessingResult, OperationalEvent, OperationalStateError, StateUpdate


class OperationalEventProcessor:
    def __init__(self, engine: StateUpdateEngine) -> None:
        self.engine = engine

    def process(self, event: OperationalEvent) -> EventProcessingResult:
        update = self._event_to_update(event)
        return EventProcessingResult(event=event, update_result=self.engine.process(update))

    def process_many(
        self,
        events: tuple[OperationalEvent, ...],
    ) -> tuple[EventProcessingResult, ...]:
        ordered = tuple(sorted(events, key=lambda item: (item.sequence, item.event_id)))
        return tuple(self.process(event) for event in ordered)

    def _event_to_update(self, event: OperationalEvent) -> StateUpdate:
        payload = dict(event.payload)
        if event.event_type == "switch_operation":
            return _state_update(
                event,
                switch_status=_required_text(payload, "status"),
                available=payload.get("available"),
            )
        if event.event_type == "breaker_operation":
            return _state_update(
                event,
                breaker_status=_required_text(payload, "status"),
                available=payload.get("available"),
            )
        if event.event_type == "alarm":
            flags = frozenset(str(item) for item in payload.get("flags", ("alarm",)))
            return _state_update(event, available=False, flags=flags)
        if event.event_type == "telemetry":
            return _state_update(
                event,
                energized=payload.get("energized"),
                available=payload.get("available"),
                flags=(
                    frozenset(str(item) for item in payload.get("flags", ()))
                    if "flags" in payload
                    else None
                ),
            )
        raise OperationalStateError(f"Unsupported operational event type: {event.event_type}")


def _state_update(
    event: OperationalEvent,
    *,
    switch_status: str | None = None,
    breaker_status: str | None = None,
    energized: bool | None = None,
    available: bool | None = None,
    flags: frozenset[str] | None = None,
) -> StateUpdate:
    return StateUpdate(
        update_id=f"event:{event.event_id}",
        asset_id=event.asset_id,
        asset_kind=event.asset_kind,
        sequence=event.sequence,
        observed_at=event.observed_at,
        actor=event.actor,
        switch_status=switch_status,
        breaker_status=breaker_status,
        energized=energized,
        available=available,
        flags=flags,
        correlation_id=event.correlation_id or event.event_id,
        attrs={"event_type": event.event_type},
    )


def _required_text(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise OperationalStateError(f"Operational event missing required field: {field}")
    return value
