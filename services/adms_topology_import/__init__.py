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
from .parser import AdmsContractParserError, ParsedAdmsTopologyImport, parse_payload
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
    "AdmsTopologyMappingError",
    "AdmsTopologyStagingError",
    "AdmsTopologyValidationError",
    "ImportContext",
    "MappedTopology",
    "ParsedAdmsTopologyImport",
    "Settings",
    "StagedTopologyImport",
    "TransportRequest",
    "TransportValidationError",
    "ValidationReport",
    "build_import_context",
    "create_staged_import",
    "ensure_valid_topology",
    "mark_ready_for_publish",
    "map_topology",
    "parse_payload",
    "validate_topology",
    "validate_request",
]
