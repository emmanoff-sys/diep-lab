"""ADMS topology import package.

WP-006-07 Objective 1 establishes the import package scaffolding only. Later
objectives add contract parsing, transport, mapping, validation, staging, and
publish integration against the approved ADMS contract baseline.
"""

from __future__ import annotations

from .config import Settings
from .container import ImportContext, build_import_context
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
    "AdmsImportMetrics",
    "AdmsContractParserError",
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
    "Settings",
    "StagedTopologyImport",
    "TopologyPublishPayload",
    "TopologyPublishResult",
    "TransportRequest",
    "TransportValidationError",
    "ValidationReport",
    "audit_lifecycle_event",
    "build_import_context",
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
