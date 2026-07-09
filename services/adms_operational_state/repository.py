"""Current operational state repository and history store."""

from __future__ import annotations

from .models import (
    AssetKind,
    OperationalAssetState,
    OperationalStateError,
    StateHistoryEntry,
    StateUpdate,
    UpdateResult,
    initial_state,
)


class InMemoryOperationalStateRepository:
    """Deterministic in-memory repository for current and historical state."""

    def __init__(self) -> None:
        self._current: dict[tuple[AssetKind, str], OperationalAssetState] = {}
        self._history: list[StateHistoryEntry] = []
        self._applied_updates: set[str] = set()

    def get_state(self, asset_id: str, *, asset_kind: AssetKind) -> OperationalAssetState | None:
        return self._current.get((asset_kind, asset_id))

    def require_state(self, asset_id: str, *, asset_kind: AssetKind) -> OperationalAssetState:
        state = self.get_state(asset_id, asset_kind=asset_kind)
        if state is None:
            raise OperationalStateError(f"Unknown operational state: {asset_kind}:{asset_id}")
        return state

    def current_states(self) -> tuple[OperationalAssetState, ...]:
        return tuple(
            sorted(
                self._current.values(),
                key=lambda state: (state.asset_kind, state.asset_id),
            )
        )

    def history(self, asset_id: str | None = None) -> tuple[StateHistoryEntry, ...]:
        entries = self._history
        if asset_id is not None:
            entries = [entry for entry in entries if entry.after.asset_id == asset_id]
        return tuple(
            sorted(
                entries,
                key=lambda entry: (
                    entry.after.sequence,
                    entry.after.asset_kind,
                    entry.after.asset_id,
                    entry.update.update_id,
                ),
            )
        )

    def has_applied(self, update_id: str) -> bool:
        return update_id in self._applied_updates

    def apply(self, update: StateUpdate) -> UpdateResult:
        if self.has_applied(update.update_id):
            existing = self.get_state(update.asset_id, asset_kind=update.asset_kind)
            return UpdateResult(
                update=update,
                accepted=True,
                duplicate=True,
                reason="duplicate_update_suppressed",
                before=existing,
                after=existing,
            )

        key = (update.asset_kind, update.asset_id)
        before = self._current.get(key)
        if before is not None and update.sequence <= before.sequence:
            return UpdateResult(
                update=update,
                accepted=False,
                duplicate=False,
                reason="stale_update_sequence",
                before=before,
                after=before,
            )

        after = (
            before.with_update(update)
            if before is not None
            else initial_state(
                asset_id=update.asset_id,
                asset_kind=update.asset_kind,
                sequence=update.sequence,
                observed_at=update.observed_at,
                actor=update.actor,
                switch_status=update.switch_status,
                breaker_status=update.breaker_status,
                energized=update.energized,
                available=update.available if update.available is not None else True,
                flags=frozenset(update.flags or frozenset()),
                correlation_id=update.correlation_id,
                attrs=update.attrs,
            )
        )
        self._current[key] = after
        self._applied_updates.add(update.update_id)
        self._history.append(StateHistoryEntry(update=update, before=before, after=after))
        return UpdateResult(
            update=update,
            accepted=True,
            duplicate=False,
            reason=None,
            before=before,
            after=after,
        )

    def replay_until(self, sequence: int) -> InMemoryOperationalStateRepository:
        replayed = InMemoryOperationalStateRepository()
        for entry in self.history():
            if entry.update.sequence <= sequence:
                replayed.apply(entry.update)
        return replayed
