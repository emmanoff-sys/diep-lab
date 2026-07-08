"""Operational network state models for WP-008."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

AssetKind = Literal["node", "edge"]
StateValue = Literal["open", "closed", "unknown"]
EventType = Literal["switch_operation", "breaker_operation", "alarm", "telemetry"]

STATE_OPEN: StateValue = "open"
STATE_CLOSED: StateValue = "closed"
STATE_UNKNOWN: StateValue = "unknown"


class OperationalStateError(ValueError):
    """Raised when operational state cannot be applied deterministically."""


@dataclass(frozen=True)
class OperationalAssetState:
    asset_id: str
    asset_kind: AssetKind
    sequence: int
    observed_at: str
    updated_by: str
    switch_status: StateValue | None = None
    breaker_status: StateValue | None = None
    energized: bool | None = None
    available: bool = True
    flags: frozenset[str] = frozenset()
    correlation_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def with_update(self, update: StateUpdate) -> OperationalAssetState:
        return replace(
            self,
            sequence=update.sequence,
            observed_at=update.observed_at,
            updated_by=update.actor,
            switch_status=(
                update.switch_status if update.switch_status is not None else self.switch_status
            ),
            breaker_status=(
                update.breaker_status if update.breaker_status is not None else self.breaker_status
            ),
            energized=update.energized if update.energized is not None else self.energized,
            available=update.available if update.available is not None else self.available,
            flags=frozenset(update.flags) if update.flags is not None else self.flags,
            correlation_id=update.correlation_id or self.correlation_id,
            attrs={**self.attrs, **update.attrs},
        )


@dataclass(frozen=True)
class StateUpdate:
    update_id: str
    asset_id: str
    asset_kind: AssetKind
    sequence: int
    observed_at: str
    actor: str
    switch_status: StateValue | None = None
    breaker_status: StateValue | None = None
    energized: bool | None = None
    available: bool | None = None
    flags: frozenset[str] | None = None
    correlation_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def has_state_delta(self) -> bool:
        return any(
            value is not None
            for value in (
                self.switch_status,
                self.breaker_status,
                self.energized,
                self.available,
                self.flags,
            )
        ) or bool(self.attrs)


@dataclass(frozen=True)
class StateHistoryEntry:
    update: StateUpdate
    before: OperationalAssetState | None
    after: OperationalAssetState
    duplicate: bool = False


@dataclass(frozen=True)
class UpdateResult:
    update: StateUpdate
    accepted: bool
    duplicate: bool
    reason: str | None
    before: OperationalAssetState | None
    after: OperationalAssetState | None


@dataclass(frozen=True)
class OperationalEvent:
    event_id: str
    event_type: EventType
    asset_id: str
    asset_kind: AssetKind
    sequence: int
    observed_at: str
    actor: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None


@dataclass(frozen=True)
class EventProcessingResult:
    event: OperationalEvent
    update_result: UpdateResult


@dataclass(frozen=True)
class ValidationDiagnostic:
    reason_code: str
    description: str
    asset_id: str | None = None
    asset_kind: AssetKind | None = None


@dataclass(frozen=True)
class ValidationReport:
    diagnostics: tuple[ValidationDiagnostic, ...]

    @property
    def is_valid(self) -> bool:
        return not self.diagnostics

    def raise_if_invalid(self) -> None:
        if self.diagnostics:
            first = self.diagnostics[0]
            raise OperationalStateError(f"{first.reason_code}: {first.description}")


def initial_state(
    *,
    asset_id: str,
    asset_kind: AssetKind,
    sequence: int,
    observed_at: str,
    actor: str,
    switch_status: StateValue | None = None,
    breaker_status: StateValue | None = None,
    energized: bool | None = None,
    available: bool = True,
    flags: frozenset[str] = frozenset(),
    correlation_id: str | None = None,
    attrs: dict[str, Any] | None = None,
) -> OperationalAssetState:
    return OperationalAssetState(
        asset_id=asset_id,
        asset_kind=asset_kind,
        sequence=sequence,
        observed_at=observed_at,
        updated_by=actor,
        switch_status=switch_status,
        breaker_status=breaker_status,
        energized=energized,
        available=available,
        flags=flags,
        correlation_id=correlation_id,
        attrs=dict(attrs or {}),
    )
