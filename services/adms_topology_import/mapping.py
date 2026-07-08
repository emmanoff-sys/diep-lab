"""Mapping from parsed ADMS contract objects to internal topology rows.

Objective 4 is deliberately transformation-only. It maps the immutable parsed
contract model into the dictionary shapes consumed by the existing topology
import/publish paths. It does not validate graph correctness, persist rows,
stage imports, publish versions, or orchestrate runtime imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .parser import MetadataEntry, ParsedAdmsEdge, ParsedAdmsNode, ParsedAdmsTopologyImport

ERROR_CATEGORY_MAPPING = "mapping"
INTERNAL_ID_PREFIX = "adms"

NODE_TYPE_MAP = {
    "bus": "bus",
    "node": "bus",
    "junction": "bus",
    "substation": "substation",
    "feeder": "feeder",
    "transformer": "transformer",
    "switch": "switch",
    "meter": "meter",
    "der": "der",
    "load": "load",
}
EDGE_TYPE_MAP = {
    "line": "line",
    "cable": "line",
    "conductor": "line",
    "switch": "switch",
    "breaker": "switch",
    "transformer": "transformer",
    "tie": "tie",
}
_ID_SAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


@dataclass(frozen=True)
class MappingDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsTopologyMappingError(ValueError):
    """Deterministic mapping error for unsupported field transformations."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_MAPPING}:{reason_code}: {description}")
        self.diagnostic = MappingDiagnostic(
            category=ERROR_CATEGORY_MAPPING,
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
class MappedTopology:
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    source_system: str
    external_model_id: str
    external_model_version: str


def map_topology(parsed: ParsedAdmsTopologyImport) -> MappedTopology:
    """Map a parsed ADMS import document to internal topology row dictionaries."""

    nodes = tuple(map_node(node, parsed) for node in parsed.nodes)
    edges = tuple(map_edge(edge, parsed) for edge in parsed.edges)
    return MappedTopology(
        nodes=nodes,
        edges=edges,
        source_system=parsed.source_system,
        external_model_id=parsed.external_model.model_id,
        external_model_version=parsed.external_model.model_version,
    )


def map_node(node: ParsedAdmsNode, parsed: ParsedAdmsTopologyImport) -> dict[str, Any]:
    """Map a parsed ADMS node into the internal grid_nodes dictionary shape."""

    return {
        "node_id": transform_identity("node", node.external_id),
        "node_type": _map_node_type(node.node_type, node.external_id),
        "name": node.name,
        "latitude": node.latitude,
        "longitude": node.longitude,
        "nominal_kv": node.nominal_kv,
        "phases": node.phases,
        "attrs": _attrs(parsed, node.metadata, node.external_id),
    }


def map_edge(edge: ParsedAdmsEdge, parsed: ParsedAdmsTopologyImport) -> dict[str, Any]:
    """Map a parsed ADMS edge into the internal grid_edges dictionary shape."""

    return {
        "edge_id": transform_identity("edge", edge.external_id),
        "from_node": transform_identity("node", edge.from_node),
        "to_node": transform_identity("node", edge.to_node),
        "edge_type": _map_edge_type(edge.edge_type, edge.external_id),
        "is_switchable": edge.is_switchable,
        "normally_closed": edge.normally_closed,
        "is_closed": edge.is_closed,
        "rating_kw": edge.rating_kw,
        "phases": edge.phases,
        "attrs": _attrs(parsed, edge.metadata, edge.external_id),
    }


def transform_identity(kind: str, external_id: str) -> str:
    """Return a deterministic internal identifier for an ADMS object."""

    cleaned = _ID_SAFE.sub("-", external_id.strip()).strip("-")
    if not cleaned:
        _raise(
            "empty_transformed_identifier",
            "ADMS external identifier cannot be transformed into an internal identifier",
            offending_object=external_id,
            location=f"{kind}.external_id",
        )
    return f"{INTERNAL_ID_PREFIX}:{kind}:{cleaned}"


def _map_node_type(node_type: str, external_id: str) -> str:
    mapped = NODE_TYPE_MAP.get(node_type.strip().lower())
    if mapped is None:
        _raise(
            "unsupported_node_type",
            f"Unsupported ADMS node type for mapping: {node_type}",
            offending_object=external_id,
            location="node.node_type",
        )
    return mapped


def _map_edge_type(edge_type: str, external_id: str) -> str:
    mapped = EDGE_TYPE_MAP.get(edge_type.strip().lower())
    if mapped is None:
        _raise(
            "unsupported_edge_type",
            f"Unsupported ADMS edge type for mapping: {edge_type}",
            offending_object=external_id,
            location="edge.edge_type",
        )
    return mapped


def _attrs(
    parsed: ParsedAdmsTopologyImport,
    metadata: tuple[MetadataEntry, ...],
    external_id: str,
) -> dict[str, Any]:
    return {
        "source": "adms",
        "source_system": parsed.source_system,
        "contract_version": parsed.contract_version,
        "correlation_id": parsed.correlation_id,
        "idempotency_key": parsed.idempotency_key,
        "external_model_id": parsed.external_model.model_id,
        "external_model_version": parsed.external_model.model_version,
        "external_model_created_at": parsed.external_model.created_at,
        "external_id": external_id,
        "metadata": {entry.key: entry.value for entry in metadata},
    }


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsTopologyMappingError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
