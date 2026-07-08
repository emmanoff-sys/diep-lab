"""Non-invasive observability helpers for ADMS topology import.

Objective 8 produces structured logging payloads, metric recording helpers,
audit event payloads, correlation context, and operational diagnostics without
changing the behaviour of parser, transport, mapping, validation, staging, or
publish workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from .metrics import AdmsImportMetrics
from .staging import StagedTopologyImport
from .transport import TransportValidationResult
from .validation import ValidationReport

ERROR_CATEGORY_OBSERVABILITY = "observability"
AUDIT_NAMESPACE = UUID("9a8c12f6-26e5-4ef1-b7e7-0ca405bc6b61")
SERVICE_NAME = "adms-topology-import"


@dataclass(frozen=True)
class ObservabilityDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsObservabilityError(ValueError):
    """Deterministic observability error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_OBSERVABILITY}:{reason_code}: {description}")
        self.diagnostic = ObservabilityDiagnostic(
            category=ERROR_CATEGORY_OBSERVABILITY,
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
class CorrelationContext:
    correlation_id: str
    idempotency_key: str | None = None
    staging_id: str | None = None
    external_model_id: str | None = None
    external_model_version: str | None = None


@dataclass(frozen=True)
class AuditEventPayload:
    event_type: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    correlation_id: str
    service_name: str
    metadata: dict[str, Any]


def correlation_from_transport(result: TransportValidationResult) -> CorrelationContext:
    """Build correlation context from Objective 3 transport validation output."""

    return CorrelationContext(
        correlation_id=result.correlation_id,
        idempotency_key=result.idempotency_key,
    )


def correlation_for_staged(
    staged: StagedTopologyImport,
    *,
    correlation_id: str,
    idempotency_key: str | None = None,
) -> CorrelationContext:
    """Build correlation context for a staged import."""

    return CorrelationContext(
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        staging_id=staged.staging_id,
        external_model_id=staged.topology.external_model_id,
        external_model_version=staged.topology.external_model_version,
    )


def structured_log_event(
    event: str,
    *,
    context: CorrelationContext,
    level: str = "info",
    **fields: Any,
) -> dict[str, Any]:
    """Return a structured log event payload for a caller-owned logger."""

    if not event.strip():
        _raise(
            "missing_log_event",
            "Structured log event name must be non-empty",
            offending_object=event,
            location="event",
        )
    return {
        "event": event,
        "level": level,
        "service": SERVICE_NAME,
        "correlation_id": context.correlation_id,
        "idempotency_key": context.idempotency_key,
        "staging_id": context.staging_id,
        "external_model_id": context.external_model_id,
        "external_model_version": context.external_model_version,
        **fields,
    }


def audit_lifecycle_event(
    staged: StagedTopologyImport,
    *,
    correlation_id: str,
    action: str,
    outcome: str = "success",
    metadata: dict[str, Any] | None = None,
) -> AuditEventPayload:
    """Build an audit event payload for a significant lifecycle transition."""

    if not correlation_id.strip():
        _raise(
            "missing_correlation_id",
            "Audit lifecycle events require a correlation id",
            offending_object=staged.staging_id,
            location="correlation_id",
        )
    event_type = f"adms.topology_import.{staged.status}"
    combined_metadata = {
        "staging_id": staged.staging_id,
        "status": staged.status,
        "external_model_id": staged.topology.external_model_id,
        "external_model_version": staged.topology.external_model_version,
        "node_count": len(staged.topology.nodes),
        "edge_count": len(staged.topology.edges),
        **(metadata or {}),
    }
    return AuditEventPayload(
        event_type=event_type,
        action=action,
        resource_type="topology_import",
        resource_id=staged.staging_id,
        outcome=outcome,
        correlation_id=correlation_id,
        service_name=SERVICE_NAME,
        metadata=combined_metadata,
    )


def deterministic_audit_event_id(payload: AuditEventPayload) -> UUID:
    """Return a deterministic UUID for idempotent audit-event emission."""

    material = "|".join(
        [
            payload.event_type,
            payload.action,
            payload.resource_id,
            payload.outcome,
            payload.correlation_id,
        ]
    )
    return uuid5(AUDIT_NAMESPACE, material)


def record_lifecycle_metrics(
    metrics: AdmsImportMetrics,
    *,
    status: str,
    outcome: str = "success",
) -> None:
    """Record lifecycle metrics without changing workflow behaviour."""

    metrics.lifecycle_events_total.labels(status=status, outcome=outcome).inc()


def record_validation_metrics(metrics: AdmsImportMetrics, report: ValidationReport) -> None:
    """Record validation failure metrics from an existing validation report."""

    for diagnostic in report.diagnostics:
        metrics.validation_failures_total.labels(reason_code=diagnostic.reason_code).inc()


def health_snapshot(
    *,
    metrics_enabled: bool,
    ready: bool = True,
    detail: str | None = None,
) -> dict[str, Any]:
    """Return operational health diagnostics for the import subsystem."""

    return {
        "service": SERVICE_NAME,
        "ready": ready,
        "metrics_enabled": metrics_enabled,
        "detail": detail,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsObservabilityError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
