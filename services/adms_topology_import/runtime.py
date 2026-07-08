"""Runtime orchestration for ADMS topology imports.

WP-006-08 Objective 11 coordinates the existing WP-006-07 layers in a
deterministic execution order. It does not add persistence, APIs, background
workers, scheduling, or alternative topology publish behaviour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .mapping import MappedTopology, map_topology
from .observability import (
    AuditEventPayload,
    CorrelationContext,
    audit_lifecycle_event,
    correlation_for_staged,
    correlation_from_transport,
    structured_log_event,
)
from .parser import ParsedAdmsTopologyImport, parse_payload
from .publish import PublishedTopologyImport, TopologyPublishGateway, publish_staged_import
from .staging import StagedTopologyImport, create_staged_import, mark_ready_for_publish
from .transport import (
    IdempotencyStore,
    TransportRequest,
    TransportValidationResult,
    validate_request,
)
from .validation import ensure_valid_topology

ERROR_CATEGORY_RUNTIME = "runtime"
STATUS_PUBLISHED = "published"
STATUS_REPLAYED = "replayed"

STEP_TRANSPORT = "transport"
STEP_REPLAY = "replay"
STEP_PARSE = "parse"
STEP_MAP = "map"
STEP_VALIDATE = "validate"
STEP_STAGE = "stage"
STEP_READY_FOR_PUBLISH = "ready_for_publish"
STEP_PUBLISH = "publish"

RUNTIME_PIPELINE = (
    STEP_TRANSPORT,
    STEP_PARSE,
    STEP_MAP,
    STEP_VALIDATE,
    STEP_STAGE,
    STEP_READY_FOR_PUBLISH,
    STEP_PUBLISH,
)


@dataclass(frozen=True)
class RuntimeDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsImportRuntimeError(ValueError):
    """Deterministic runtime orchestration error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_RUNTIME}:{reason_code}: {description}")
        self.diagnostic = RuntimeDiagnostic(
            category=ERROR_CATEGORY_RUNTIME,
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
class RuntimeExecutionOptions:
    actor: str = "adms-runtime"
    label: str | None = None
    description: str | None = None
    site_name: str | None = None
    staging_id: str | None = None


@dataclass(frozen=True)
class RuntimeDependencies:
    settings: type[Settings]
    logger: logging.Logger
    metrics: Any
    publish_gateway: TopologyPublishGateway | None = None
    idempotency_store: IdempotencyStore | None = None


@dataclass(frozen=True)
class RuntimeExecutionResult:
    status: str
    steps_completed: tuple[str, ...]
    transport: TransportValidationResult
    correlation: CorrelationContext
    parsed: ParsedAdmsTopologyImport | None = None
    mapped: MappedTopology | None = None
    staged: StagedTopologyImport | None = None
    published: PublishedTopologyImport | None = None
    log_events: tuple[dict[str, Any], ...] = ()
    audit_events: tuple[AuditEventPayload, ...] = ()


class RuntimeWorkflowController:
    """Execute the ADMS import lifecycle in the authorised deterministic order."""

    def __init__(self, dependencies: RuntimeDependencies) -> None:
        self._dependencies = dependencies

    @property
    def pipeline(self) -> tuple[str, ...]:
        return RUNTIME_PIPELINE

    def execute(
        self,
        request: TransportRequest,
        *,
        options: RuntimeExecutionOptions | None = None,
    ) -> RuntimeExecutionResult:
        resolved_options = options or RuntimeExecutionOptions()
        steps: list[str] = []

        transport = validate_request(
            request,
            settings=self._dependencies.settings,
            idempotency_store=self._dependencies.idempotency_store,
        )
        steps.append(STEP_TRANSPORT)
        transport_correlation = correlation_from_transport(transport)
        if transport.replay:
            steps.append(STEP_REPLAY)
            log_event = structured_log_event(
                "adms.import.replayed",
                context=transport_correlation,
                status=STATUS_REPLAYED,
            )
            self._emit_log(log_event)
            return RuntimeExecutionResult(
                status=STATUS_REPLAYED,
                steps_completed=tuple(steps),
                transport=transport,
                correlation=transport_correlation,
                log_events=(log_event,),
            )

        parsed = parse_payload(transport.body)
        steps.append(STEP_PARSE)

        mapped = map_topology(parsed)
        steps.append(STEP_MAP)

        mapped = ensure_valid_topology(mapped)
        steps.append(STEP_VALIDATE)

        staged = create_staged_import(
            mapped,
            staging_id=resolved_options.staging_id,
            actor=resolved_options.actor,
        )
        steps.append(STEP_STAGE)

        staged = mark_ready_for_publish(staged, actor=resolved_options.actor)
        steps.append(STEP_READY_FOR_PUBLISH)

        gateway = self._dependencies.publish_gateway
        if gateway is None:
            _raise(
                "missing_publish_gateway",
                "Runtime orchestration requires an injected governed publish gateway",
                offending_object="publish_gateway",
                location="dependencies.publish_gateway",
            )

        published = publish_staged_import(
            staged,
            gateway,
            actor=resolved_options.actor,
            label=resolved_options.label,
            description=resolved_options.description,
            site_name=resolved_options.site_name,
        )
        steps.append(STEP_PUBLISH)

        published_correlation = correlation_for_staged(
            published.staged,
            correlation_id=transport.correlation_id,
            idempotency_key=transport.idempotency_key,
        )
        log_event = structured_log_event(
            "adms.import.published",
            context=published_correlation,
            status=published.staged.status,
            published_version=published.published_version,
        )
        audit_event = audit_lifecycle_event(
            published.staged,
            correlation_id=transport.correlation_id,
            action="topology_import.publish",
        )
        self._emit_log(log_event)
        return RuntimeExecutionResult(
            status=STATUS_PUBLISHED,
            steps_completed=tuple(steps),
            transport=transport,
            correlation=published_correlation,
            parsed=parsed,
            mapped=mapped,
            staged=published.staged,
            published=published,
            log_events=(log_event,),
            audit_events=(audit_event,),
        )

    def _emit_log(self, event: dict[str, Any]) -> None:
        self._dependencies.logger.info(event)


@dataclass(frozen=True)
class AdmsImportCoordinator:
    """Coordinator facade for runtime import execution."""

    controller: RuntimeWorkflowController

    def submit(
        self,
        request: TransportRequest,
        *,
        options: RuntimeExecutionOptions | None = None,
    ) -> RuntimeExecutionResult:
        """Execute one ADMS import request through the runtime workflow."""

        return self.controller.execute(request, options=options)


def build_runtime_dependencies(
    *,
    settings: type[Settings] = Settings,
    logger: logging.Logger | None = None,
    metrics: Any = None,
    publish_gateway: TopologyPublishGateway | None = None,
    idempotency_store: IdempotencyStore | None = None,
) -> RuntimeDependencies:
    """Build runtime dependencies without opening external resources."""

    return RuntimeDependencies(
        settings=settings,
        logger=logger or logging.getLogger("diep-adms-topology-import"),
        metrics=metrics,
        publish_gateway=publish_gateway,
        idempotency_store=idempotency_store,
    )


def build_import_coordinator(dependencies: RuntimeDependencies) -> AdmsImportCoordinator:
    """Build the import coordinator around an injected workflow controller."""

    return AdmsImportCoordinator(controller=RuntimeWorkflowController(dependencies))


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportRuntimeError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
