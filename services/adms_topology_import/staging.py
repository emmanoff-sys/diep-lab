"""In-memory staging workflow for ADMS topology imports.

Objective 6 coordinates validated topology data through staging lifecycle
states only. It does not persist staged data, publish topology versions,
schedule background work, expose APIs, or communicate with an external ADMS.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

from .mapping import MappedTopology
from .validation import ValidationReport, validate_topology

ERROR_CATEGORY_STAGING = "staging"

STATUS_STAGED = "staged"
STATUS_READY_FOR_PUBLISH = "ready_for_publish"
STATUS_ROLLBACK_REQUESTED = "rollback_requested"
STATUS_ROLLED_BACK = "rolled_back"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = frozenset({STATUS_ROLLED_BACK, STATUS_CANCELLED})
ALLOWED_TRANSITIONS = {
    STATUS_STAGED: frozenset(
        {STATUS_READY_FOR_PUBLISH, STATUS_ROLLBACK_REQUESTED, STATUS_CANCELLED}
    ),
    STATUS_READY_FOR_PUBLISH: frozenset({STATUS_ROLLBACK_REQUESTED, STATUS_CANCELLED}),
    STATUS_ROLLBACK_REQUESTED: frozenset({STATUS_ROLLED_BACK, STATUS_CANCELLED}),
    STATUS_ROLLED_BACK: frozenset(),
    STATUS_CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class StagingDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsTopologyStagingError(ValueError):
    """Deterministic staging lifecycle error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_STAGING}:{reason_code}: {description}")
        self.diagnostic = StagingDiagnostic(
            category=ERROR_CATEGORY_STAGING,
            reason_code=reason_code,
            description=description,
            offending_object=offending_object,
            location=location,
        )

    @property
    def category(self) -> str:
        return self.diagnostic.category

    @property
    def reason_code(self) -> str:
        return self.diagnostic.reason_code

    @property
    def description(self) -> str:
        return self.diagnostic.description

    @property
    def offending_object(self) -> str | None:
        return self.diagnostic.offending_object

    @property
    def location(self) -> str | None:
        return self.diagnostic.location


@dataclass(frozen=True)
class StagingEvent:
    from_status: str | None
    to_status: str
    reason: str
    actor: str


@dataclass(frozen=True)
class StagedTopologyImport:
    staging_id: str
    status: str
    topology: MappedTopology
    validation_report: ValidationReport
    lifecycle: tuple[StagingEvent, ...]
    rollback_reason: str | None = None
    rollback_target_version: int | None = None


def create_staged_import(
    topology: MappedTopology,
    *,
    staging_id: str | None = None,
    actor: str = "adms-import",
) -> StagedTopologyImport:
    """Create a staged import from validated mapped topology data."""

    validation_report = validate_topology(topology)
    if not validation_report.is_valid:
        _raise(
            "invalid_topology_for_staging",
            "Only valid mapped topology can be staged",
            offending_object=topology.external_model_id,
            location="topology",
        )
    resolved_id = staging_id or derive_staging_id(topology)
    _validate_staging_id(resolved_id)
    return StagedTopologyImport(
        staging_id=resolved_id,
        status=STATUS_STAGED,
        topology=topology,
        validation_report=validation_report,
        lifecycle=(
            StagingEvent(
                from_status=None,
                to_status=STATUS_STAGED,
                reason="staged_validated_topology",
                actor=actor,
            ),
        ),
    )


def mark_ready_for_publish(
    staged: StagedTopologyImport,
    *,
    actor: str = "adms-import",
) -> StagedTopologyImport:
    """Move a staged import to ready-for-publish status without publishing."""

    return transition(staged, STATUS_READY_FOR_PUBLISH, reason="validated_for_publish", actor=actor)


def request_rollback(
    staged: StagedTopologyImport,
    *,
    reason: str,
    target_version: int | None = None,
    actor: str = "adms-import",
) -> StagedTopologyImport:
    """Coordinate rollback intent inside the staging context."""

    if not reason.strip():
        _raise(
            "missing_rollback_reason",
            "Rollback request requires a reason",
            offending_object=staged.staging_id,
            location="rollback_reason",
        )
    if target_version is not None and target_version < 1:
        _raise(
            "invalid_rollback_target",
            "Rollback target version must be a positive integer",
            offending_object=str(target_version),
            location="rollback_target_version",
        )
    updated = transition(
        staged,
        STATUS_ROLLBACK_REQUESTED,
        reason="rollback_requested",
        actor=actor,
    )
    return replace(
        updated,
        rollback_reason=reason,
        rollback_target_version=target_version,
    )


def complete_rollback(
    staged: StagedTopologyImport,
    *,
    actor: str = "adms-import",
) -> StagedTopologyImport:
    """Mark staged rollback coordination complete without touching production state."""

    if staged.status != STATUS_ROLLBACK_REQUESTED:
        _raise(
            "rollback_not_requested",
            "Rollback can only complete after rollback has been requested",
            offending_object=staged.staging_id,
            location="status",
        )
    return transition(staged, STATUS_ROLLED_BACK, reason="rollback_completed", actor=actor)


def cancel_staging(
    staged: StagedTopologyImport,
    *,
    reason: str,
    actor: str = "adms-import",
) -> StagedTopologyImport:
    """Cancel a staged import before any future publish integration consumes it."""

    if not reason.strip():
        _raise(
            "missing_cancel_reason",
            "Cancellation requires a reason",
            offending_object=staged.staging_id,
            location="cancel_reason",
        )
    return transition(staged, STATUS_CANCELLED, reason=reason, actor=actor)


def transition(
    staged: StagedTopologyImport,
    to_status: str,
    *,
    reason: str,
    actor: str = "adms-import",
) -> StagedTopologyImport:
    """Apply a deterministic lifecycle transition to a staged import."""

    if staged.status not in ALLOWED_TRANSITIONS:
        _raise(
            "unknown_current_status",
            f"Unknown staging status: {staged.status}",
            offending_object=staged.staging_id,
            location="status",
        )
    if to_status not in ALLOWED_TRANSITIONS[staged.status]:
        _raise(
            "invalid_status_transition",
            f"Cannot transition staging status from {staged.status} to {to_status}",
            offending_object=staged.staging_id,
            location="status",
        )
    if not reason.strip():
        _raise(
            "missing_transition_reason",
            "Lifecycle transition requires a reason",
            offending_object=staged.staging_id,
            location="reason",
        )
    event = StagingEvent(
        from_status=staged.status,
        to_status=to_status,
        reason=reason,
        actor=actor,
    )
    return replace(
        staged,
        status=to_status,
        lifecycle=(*staged.lifecycle, event),
    )


def derive_staging_id(topology: MappedTopology) -> str:
    """Derive a deterministic staging id from model identity and row ids."""

    material: list[str] = [
        topology.source_system,
        topology.external_model_id,
        topology.external_model_version,
    ]
    material.extend(str(node.get("node_id", "")) for node in topology.nodes)
    material.extend(str(edge.get("edge_id", "")) for edge in topology.edges)
    digest = hashlib.sha256("|".join(material).encode("utf-8")).hexdigest()[:16]
    return f"stage-{digest}"


def staged_summary(staged: StagedTopologyImport) -> dict[str, Any]:
    """Return non-persistent status evidence for governance/reporting."""

    return {
        "staging_id": staged.staging_id,
        "status": staged.status,
        "source_system": staged.topology.source_system,
        "external_model_id": staged.topology.external_model_id,
        "external_model_version": staged.topology.external_model_version,
        "node_count": len(staged.topology.nodes),
        "edge_count": len(staged.topology.edges),
        "rollback_target_version": staged.rollback_target_version,
        "lifecycle": tuple(event.to_status for event in staged.lifecycle),
    }


def _validate_staging_id(staging_id: str) -> None:
    if not staging_id.strip():
        _raise(
            "invalid_staging_id",
            "Staging id must be non-empty",
            offending_object=staging_id,
            location="staging_id",
        )


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsTopologyStagingError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
