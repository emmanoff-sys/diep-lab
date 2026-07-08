"""Consistency validation between operational state and topology."""

from __future__ import annotations

from services.adms_topology_services import InMemoryTopologyRepository

from .models import (
    OperationalAssetState,
    StateUpdate,
    ValidationDiagnostic,
    ValidationReport,
)

VALID_STATES = frozenset({"open", "closed", "unknown"})


class OperationalStateValidator:
    def __init__(self, topology: InMemoryTopologyRepository) -> None:
        self.topology = topology

    def validate_update(self, update: StateUpdate) -> ValidationReport:
        diagnostics: list[ValidationDiagnostic] = []
        _validate_common(update, diagnostics)
        self._validate_asset(update.asset_kind, update.asset_id, diagnostics)
        self._validate_operational_fields(update, diagnostics)
        return ValidationReport(tuple(diagnostics))

    def validate_repository(
        self,
        states: tuple[OperationalAssetState, ...],
    ) -> ValidationReport:
        diagnostics: list[ValidationDiagnostic] = []
        for state in states:
            self._validate_asset(state.asset_kind, state.asset_id, diagnostics)
            self._validate_edge_state_consistency(state, diagnostics)
        return ValidationReport(tuple(diagnostics))

    def _validate_asset(
        self,
        asset_kind: str,
        asset_id: str,
        diagnostics: list[ValidationDiagnostic],
    ) -> None:
        if asset_kind == "node":
            if self.topology.get_node(asset_id) is None:
                diagnostics.append(
                    _diagnostic("orphaned_state", "State references unknown node", asset_id, "node")
                )
            return
        if asset_kind == "edge":
            if self.topology.get_edge(asset_id) is None:
                diagnostics.append(
                    _diagnostic("orphaned_state", "State references unknown edge", asset_id, "edge")
                )
            return
        diagnostics.append(
            _diagnostic("invalid_asset_kind", "State asset kind must be node or edge", asset_id)
        )

    def _validate_operational_fields(
        self,
        update: StateUpdate,
        diagnostics: list[ValidationDiagnostic],
    ) -> None:
        if update.switch_status is not None and update.switch_status not in VALID_STATES:
            diagnostics.append(
                _diagnostic(
                    "invalid_switch_status",
                    "Switch status must be open, closed, or unknown",
                    update.asset_id,
                    update.asset_kind,
                )
            )
        if update.breaker_status is not None and update.breaker_status not in VALID_STATES:
            diagnostics.append(
                _diagnostic(
                    "invalid_breaker_status",
                    "Breaker status must be open, closed, or unknown",
                    update.asset_id,
                    update.asset_kind,
                )
            )
        if update.asset_kind == "edge" and update.switch_status is not None:
            edge = self.topology.get_edge(update.asset_id)
            if edge is not None and not edge.is_switchable:
                diagnostics.append(
                    _diagnostic(
                        "non_switchable_edge_state",
                        "Switch status cannot be applied to a non-switchable edge",
                        update.asset_id,
                        "edge",
                    )
                )

    def _validate_edge_state_consistency(
        self,
        state: OperationalAssetState,
        diagnostics: list[ValidationDiagnostic],
    ) -> None:
        if state.asset_kind != "edge":
            return
        edge = self.topology.get_edge(state.asset_id)
        if edge is None:
            return
        if state.switch_status is not None and not edge.is_switchable:
            diagnostics.append(
                _diagnostic(
                    "non_switchable_edge_state",
                    "Switch status cannot be applied to a non-switchable edge",
                    state.asset_id,
                    "edge",
                )
            )
        if state.energized is True and _edge_is_open(state):
            diagnostics.append(
                _diagnostic(
                    "open_edge_marked_energized",
                    "Open edge cannot be marked energized",
                    state.asset_id,
                    "edge",
                )
            )


def _validate_common(update: StateUpdate, diagnostics: list[ValidationDiagnostic]) -> None:
    if not update.update_id.strip():
        diagnostics.append(
            _diagnostic("missing_update_id", "Update id is required", update.asset_id)
        )
    if not update.asset_id.strip():
        diagnostics.append(_diagnostic("missing_asset_id", "Asset id is required", update.asset_id))
    if update.sequence < 0:
        diagnostics.append(
            _diagnostic(
                "invalid_sequence",
                "Update sequence must be non-negative",
                update.asset_id,
                update.asset_kind,
            )
        )
    if not update.has_state_delta():
        diagnostics.append(
            _diagnostic(
                "empty_update",
                "Update must contain at least one operational state delta",
                update.asset_id,
                update.asset_kind,
            )
        )


def _edge_is_open(state: OperationalAssetState) -> bool:
    return state.switch_status == "open" or state.breaker_status == "open"


def _diagnostic(
    reason_code: str,
    description: str,
    asset_id: str | None,
    asset_kind: str | None = None,
) -> ValidationDiagnostic:
    return ValidationDiagnostic(
        reason_code=reason_code,
        description=description,
        asset_id=asset_id,
        asset_kind=asset_kind if asset_kind in {"node", "edge"} else None,
    )
