"""Deterministic parser for the ADMS topology import contract v1.0.

Objective 2 is intentionally parser-local. This module performs payload
reading, contract version checks, schema validation, mandatory field
validation, duplicate identifier checks, and immutable parsed-model creation.
It does not perform transport, authentication, topology mapping, persistence,
staging, publishing, or runtime ADMS communication.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .config import Settings

JsonObject = Mapping[str, Any]

ERROR_CATEGORY_PAYLOAD = "payload"
ERROR_CATEGORY_CONTRACT = "contract"
ERROR_CATEGORY_SCHEMA = "schema"

IMPORT_MODE_FULL_SNAPSHOT = "full_snapshot"
SUPPORTED_IMPORT_MODES = (IMPORT_MODE_FULL_SNAPSHOT,)

SUPPORTED_TOPOLOGY_COLLECTIONS = ("nodes", "edges")
REQUIRED_TOP_LEVEL_FIELDS = (
    "contract_version",
    "source_system",
    "correlation_id",
    "idempotency_key",
    "import_mode",
    "external_model",
    "topology",
)
REQUIRED_EXTERNAL_MODEL_FIELDS = ("model_id", "model_version", "created_at")
REQUIRED_NODE_FIELDS = (
    "external_id",
    "node_type",
    "name",
    "latitude",
    "longitude",
    "nominal_kv",
    "phases",
    "metadata",
)
REQUIRED_EDGE_FIELDS = (
    "external_id",
    "from_node",
    "to_node",
    "edge_type",
    "is_switchable",
    "normally_closed",
    "is_closed",
    "rating_kw",
    "phases",
    "metadata",
)
STRING_FIELDS = {
    "contract_version",
    "source_system",
    "correlation_id",
    "idempotency_key",
    "import_mode",
    "model_id",
    "model_version",
    "created_at",
    "external_id",
    "node_type",
    "name",
    "edge_type",
    "from_node",
    "to_node",
    "phases",
}


@dataclass(frozen=True)
class ParserDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsContractParserError(ValueError):
    """Deterministic parser error with machine-readable diagnostics."""

    def __init__(
        self,
        *,
        category: str,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{category}:{reason_code}: {description}")
        self.diagnostic = ParserDiagnostic(
            category=category,
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
class MetadataEntry:
    key: str
    value: Any


@dataclass(frozen=True)
class ExternalModel:
    model_id: str
    model_version: str
    created_at: str


@dataclass(frozen=True)
class ParsedAdmsNode:
    external_id: str
    node_type: str
    name: str
    latitude: float
    longitude: float
    nominal_kv: float
    phases: str
    metadata: tuple[MetadataEntry, ...]


@dataclass(frozen=True)
class ParsedAdmsEdge:
    external_id: str
    from_node: str
    to_node: str
    edge_type: str
    is_switchable: bool
    normally_closed: bool
    is_closed: bool
    rating_kw: float
    phases: str
    metadata: tuple[MetadataEntry, ...]


@dataclass(frozen=True)
class ParsedAdmsTopologyImport:
    contract_version: str
    source_system: str
    correlation_id: str
    idempotency_key: str
    import_mode: str
    external_model: ExternalModel
    nodes: tuple[ParsedAdmsNode, ...]
    edges: tuple[ParsedAdmsEdge, ...]
    diagnostics: tuple[ParserDiagnostic, ...] = ()


def parse_payload(
    payload: str | bytes | bytearray | JsonObject,
    *,
    supported_versions: tuple[str, ...] | None = None,
) -> ParsedAdmsTopologyImport:
    """Parse and validate an ADMS topology import payload."""

    document = _read_payload(payload)
    versions = supported_versions or (Settings.CONTRACT_VERSION,)
    _validate_required_fields(document, REQUIRED_TOP_LEVEL_FIELDS, "$", "$")

    contract_version = _require_string(document, "contract_version", "$.contract_version")
    if contract_version not in versions:
        _raise(
            ERROR_CATEGORY_CONTRACT,
            "unsupported_contract_version",
            f"Unsupported ADMS contract version: {contract_version!r}",
            offending_object=contract_version,
            location="$.contract_version",
        )

    import_mode = _require_string(document, "import_mode", "$.import_mode")
    if import_mode not in SUPPORTED_IMPORT_MODES:
        _raise(
            ERROR_CATEGORY_CONTRACT,
            "unsupported_import_mode",
            f"Unsupported ADMS import mode: {import_mode!r}",
            offending_object=import_mode,
            location="$.import_mode",
        )

    external_model = _parse_external_model(document["external_model"])
    topology = _require_mapping(document, "topology", "$.topology")
    _validate_topology_collections(topology)

    nodes = tuple(
        _parse_node(node, index)
        for index, node in enumerate(_require_collection(topology, "nodes", "$.topology.nodes"))
    )
    edges = tuple(
        _parse_edge(edge, index)
        for index, edge in enumerate(_require_collection(topology, "edges", "$.topology.edges"))
    )
    _validate_unique_identifiers(nodes, edges)

    return ParsedAdmsTopologyImport(
        contract_version=contract_version,
        source_system=_require_string(document, "source_system", "$.source_system"),
        correlation_id=_require_string(document, "correlation_id", "$.correlation_id"),
        idempotency_key=_require_string(document, "idempotency_key", "$.idempotency_key"),
        import_mode=import_mode,
        external_model=external_model,
        nodes=nodes,
        edges=edges,
    )


def _read_payload(payload: str | bytes | bytearray | JsonObject) -> JsonObject:
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, bytes | bytearray):
        payload = payload.decode("utf-8")
    if not isinstance(payload, str):
        _raise(
            ERROR_CATEGORY_PAYLOAD,
            "unsupported_payload_type",
            "Payload must be JSON text, bytes, or a mapping",
            offending_object=type(payload).__name__,
            location="$",
        )
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        _raise(
            ERROR_CATEGORY_PAYLOAD,
            "malformed_json",
            f"Malformed JSON payload: {exc.msg}",
            offending_object="payload",
            location=f"line {exc.lineno}, column {exc.colno}",
        )
    if not isinstance(document, Mapping):
        _raise(
            ERROR_CATEGORY_SCHEMA,
            "document_not_object",
            "Payload root must be a JSON object",
            offending_object=type(document).__name__,
            location="$",
        )
    return document


def _parse_external_model(value: Any) -> ExternalModel:
    model = _require_mapping_value(value, "$.external_model")
    _validate_required_fields(
        model,
        REQUIRED_EXTERNAL_MODEL_FIELDS,
        "$.external_model",
        "external_model",
    )
    return ExternalModel(
        model_id=_require_string(model, "model_id", "$.external_model.model_id"),
        model_version=_require_string(model, "model_version", "$.external_model.model_version"),
        created_at=_require_string(model, "created_at", "$.external_model.created_at"),
    )


def _parse_node(value: Any, index: int) -> ParsedAdmsNode:
    location = f"$.topology.nodes[{index}]"
    node = _require_mapping_value(value, location)
    object_id = _object_label(node, location)
    _validate_required_fields(node, REQUIRED_NODE_FIELDS, location, object_id)
    return ParsedAdmsNode(
        external_id=_require_string(node, "external_id", f"{location}.external_id"),
        node_type=_require_string(node, "node_type", f"{location}.node_type"),
        name=_require_string(node, "name", f"{location}.name"),
        latitude=_require_number(node, "latitude", f"{location}.latitude"),
        longitude=_require_number(node, "longitude", f"{location}.longitude"),
        nominal_kv=_require_number(node, "nominal_kv", f"{location}.nominal_kv"),
        phases=_require_string(node, "phases", f"{location}.phases"),
        metadata=_parse_metadata(node["metadata"], f"{location}.metadata", object_id),
    )


def _parse_edge(value: Any, index: int) -> ParsedAdmsEdge:
    location = f"$.topology.edges[{index}]"
    edge = _require_mapping_value(value, location)
    object_id = _object_label(edge, location)
    _validate_required_fields(edge, REQUIRED_EDGE_FIELDS, location, object_id)
    return ParsedAdmsEdge(
        external_id=_require_string(edge, "external_id", f"{location}.external_id"),
        from_node=_require_string(edge, "from_node", f"{location}.from_node"),
        to_node=_require_string(edge, "to_node", f"{location}.to_node"),
        edge_type=_require_string(edge, "edge_type", f"{location}.edge_type"),
        is_switchable=_require_bool(edge, "is_switchable", f"{location}.is_switchable"),
        normally_closed=_require_bool(edge, "normally_closed", f"{location}.normally_closed"),
        is_closed=_require_bool(edge, "is_closed", f"{location}.is_closed"),
        rating_kw=_require_number(edge, "rating_kw", f"{location}.rating_kw"),
        phases=_require_string(edge, "phases", f"{location}.phases"),
        metadata=_parse_metadata(edge["metadata"], f"{location}.metadata", object_id),
    )


def _parse_metadata(value: Any, location: str, object_id: str) -> tuple[MetadataEntry, ...]:
    metadata = _require_mapping_value(value, location)
    return tuple(MetadataEntry(str(key), metadata[key]) for key in sorted(metadata))


def _validate_required_fields(
    document: JsonObject,
    required_fields: tuple[str, ...],
    location: str,
    object_id: str,
) -> None:
    for field in required_fields:
        if field not in document:
            _raise(
                ERROR_CATEGORY_SCHEMA,
                "missing_required_field",
                f"Missing required field: {field}",
                offending_object=object_id,
                location=f"{location}.{field}" if location != "$" else f"$.{field}",
            )
        if document[field] is None:
            _raise(
                ERROR_CATEGORY_SCHEMA,
                "null_required_field",
                f"Required field cannot be null: {field}",
                offending_object=object_id,
                location=f"{location}.{field}" if location != "$" else f"$.{field}",
            )


def _validate_topology_collections(topology: JsonObject) -> None:
    for key in sorted(topology):
        if key not in SUPPORTED_TOPOLOGY_COLLECTIONS:
            _raise(
                ERROR_CATEGORY_SCHEMA,
                "unexpected_topology_collection",
                f"Unexpected topology collection: {key}",
                offending_object=key,
                location=f"$.topology.{key}",
            )


def _validate_unique_identifiers(
    nodes: tuple[ParsedAdmsNode, ...],
    edges: tuple[ParsedAdmsEdge, ...],
) -> None:
    seen: set[str] = set()
    for object_id in [node.external_id for node in nodes] + [edge.external_id for edge in edges]:
        if object_id in seen:
            _raise(
                ERROR_CATEGORY_SCHEMA,
                "duplicate_identifier",
                f"Duplicate ADMS object identifier: {object_id}",
                offending_object=object_id,
                location="$.topology",
            )
        seen.add(object_id)


def _require_mapping(document: JsonObject, field: str, location: str) -> JsonObject:
    return _require_mapping_value(document[field], location)


def _require_mapping_value(value: Any, location: str) -> JsonObject:
    if not isinstance(value, Mapping):
        _raise(
            ERROR_CATEGORY_SCHEMA,
            "expected_object",
            "Expected JSON object",
            offending_object=type(value).__name__,
            location=location,
        )
    return value


def _require_collection(document: JsonObject, field: str, location: str) -> tuple[Any, ...]:
    value = document.get(field)
    if value is None:
        _raise(
            ERROR_CATEGORY_SCHEMA,
            "missing_required_field",
            f"Missing required field: {field}",
            offending_object="topology",
            location=location,
        )
    if not isinstance(value, list):
        _raise(
            ERROR_CATEGORY_SCHEMA,
            "expected_collection",
            "Expected JSON array",
            offending_object=type(value).__name__,
            location=location,
        )
    return tuple(value)


def _require_string(document: JsonObject, field: str, location: str) -> str:
    value = document[field]
    if not isinstance(value, str) or not value.strip():
        reason = "expected_string" if field in STRING_FIELDS else "invalid_string_field"
        _raise(
            ERROR_CATEGORY_SCHEMA,
            reason,
            f"Expected non-empty string for field: {field}",
            offending_object=field,
            location=location,
        )
    return value


def _require_number(document: JsonObject, field: str, location: str) -> float:
    value = document[field]
    if isinstance(value, bool) or not isinstance(value, int | float):
        _raise(
            ERROR_CATEGORY_SCHEMA,
            "expected_number",
            f"Expected number for field: {field}",
            offending_object=field,
            location=location,
        )
    return float(value)


def _require_bool(document: JsonObject, field: str, location: str) -> bool:
    value = document[field]
    if not isinstance(value, bool):
        _raise(
            ERROR_CATEGORY_SCHEMA,
            "expected_boolean",
            f"Expected boolean for field: {field}",
            offending_object=field,
            location=location,
        )
    return value


def _object_label(document: JsonObject, fallback: str) -> str:
    value = document.get("external_id")
    return value if isinstance(value, str) and value else fallback


def _raise(
    category: str,
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsContractParserError(
        category=category,
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
