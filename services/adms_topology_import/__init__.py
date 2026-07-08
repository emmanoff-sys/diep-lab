"""ADMS topology import package.

The package exposes the governed ADMS topology import foundation and the
WP-006-08 runtime coordinator that consumes it. The runtime layer orchestrates
the existing transport, parser, mapping, validation, staging, publish, and
observability components without replacing their responsibilities.
"""

from __future__ import annotations

from .config import Settings
from .container import ImportContext, build_import_context, build_runtime_coordinator
from .mapping import AdmsTopologyMappingError, MappedTopology, map_topology
from .metrics import AdmsImportMetrics
from .observability import (
    AdmsObservabilityError,
    AuditEventPayload,
    CorrelationContext,
    audit_lifecycle_event,
    correlation_from_transport,
    health_snapshot,
    structured_log_event,
)
from .parser import AdmsContractParserError, ParsedAdmsTopologyImport, parse_payload
from .publish import (
    AdmsTopologyPublishError,
    PublishedTopologyImport,
    TopologyPublishPayload,
    TopologyPublishResult,
    publish_staged_import,
)
from .runtime import (
    AdmsImportCoordinator,
    AdmsImportRuntimeError,
    RuntimeDependencies,
    RuntimeExecutionOptions,
    RuntimeExecutionResult,
    RuntimeWorkflowController,
    build_import_coordinator,
    build_runtime_dependencies,
)
from .staging import (
    AdmsTopologyStagingError,
    StagedTopologyImport,
    create_staged_import,
    mark_ready_for_publish,
)
from .transport import TransportRequest, TransportValidationError, validate_request
from .validation import (
    AdmsTopologyValidationError,
    ValidationReport,
    ensure_valid_topology,
    validate_topology,
)

__all__ = [
    "AdmsContractParserError",
    "AdmsImportCoordinator",
    "AdmsImportMetrics",
    "AdmsImportRuntimeError",
    "AdmsObservabilityError",
    "AdmsTopologyMappingError",
    "AdmsTopologyPublishError",
    "AdmsTopologyStagingError",
    "AdmsTopologyValidationError",
    "AuditEventPayload",
    "CorrelationContext",
    "ImportContext",
    "MappedTopology",
    "ParsedAdmsTopologyImport",
    "PublishedTopologyImport",
    "RuntimeDependencies",
    "RuntimeExecutionOptions",
    "RuntimeExecutionResult",
    "RuntimeWorkflowController",
    "Settings",
    "StagedTopologyImport",
    "TopologyPublishPayload",
    "TopologyPublishResult",
    "TransportRequest",
    "TransportValidationError",
    "ValidationReport",
    "audit_lifecycle_event",
    "build_import_coordinator",
    "build_import_context",
    "build_runtime_coordinator",
    "build_runtime_dependencies",
    "correlation_from_transport",
    "create_staged_import",
    "ensure_valid_topology",
    "health_snapshot",
    "mark_ready_for_publish",
    "map_topology",
    "parse_payload",
    "publish_staged_import",
    "structured_log_event",
    "validate_topology",
    "validate_request",
]
