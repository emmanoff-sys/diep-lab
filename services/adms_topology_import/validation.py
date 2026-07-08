"""Validation engine for mapped ADMS topology imports.

Objective 5 is validation-only. It checks mapped in-memory topology rows for
duplicate identifiers, missing references, malformed relationships, and bounded
business rules before any future persistence or publish workflow can consume the
data. It does not write to a database, stage imports, publish versions, expose
APIs, or orchestrate runtime imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mapping import MappedTopology

ERROR_CATEGORY_VALIDATION = "validation"
VALID_PHASES = frozenset("ABCN")


@dataclass(frozen=True)
class ValidationDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsTopologyValidationError(ValueError):
    """Raised when mapped topology validation fails."""

    def __init__(self, diagnostics: tuple[ValidationDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must contain at least one validation failure")
        super().__init__(
            f"{ERROR_CATEGORY_VALIDATION}:{diagnostics[0].reason_code}: "
            f"{diagnostics[0].description}"
        )
        self.diagnostics = diagnostics

    @property
    def diagnostic(self) -> ValidationDiagnostic:
        return self.diagnostics[0]

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
class ValidationReport:
    diagnostics: tuple[ValidationDiagnostic, ...]

    @property
    def is_valid(self) -> bool:
        return not self.diagnostics

    def raise_if_invalid(self) -> None:
        if self.diagnostics:
            raise AdmsTopologyValidationError(self.diagnostics)


def validate_topology(mapped: MappedTopology) -> ValidationReport:
    """Validate mapped topology rows and return deterministic diagnostics."""

    diagnostics: list[ValidationDiagnostic] = []
    node_ids = _validate_nodes(mapped.nodes, diagnostics)
    _validate_edges(mapped.edges, node_ids, diagnostics)
    return ValidationReport(tuple(diagnostics))


def ensure_valid_topology(mapped: MappedTopology) -> MappedTopology:
    """Raise if mapped topology is invalid; otherwise return it unchanged."""

    validate_topology(mapped).raise_if_invalid()
    return mapped


def _validate_nodes(
    nodes: tuple[dict[str, Any], ...],
    diagnostics: list[ValidationDiagnostic],
) -> set[str]:
    node_ids: set[str] = set()
    if not nodes:
        diagnostics.append(
            _diagnostic(
                "empty_topology",
                "Topology import must contain at least one node",
                offending_object="nodes",
                location="nodes",
            )
        )
        return node_ids

    for index, node in enumerate(nodes):
        location = f"nodes[{index}]"
        node_id = _required_text(node, "node_id", location, diagnostics)
        _required_text(node, "node_type", location, diagnostics)
        _validate_number(node, "latitude", location, diagnostics, minimum=-90.0, maximum=90.0)
        _validate_number(node, "longitude", location, diagnostics, minimum=-180.0, maximum=180.0)
        _validate_number(node, "nominal_kv", location, diagnostics, minimum=0.0)
        _validate_phases(node.get("phases"), node_id or location, f"{location}.phases", diagnostics)

        if not node_id:
            continue
        if node_id in node_ids:
            diagnostics.append(
                _diagnostic(
                    "duplicate_node_identifier",
                    f"Duplicate node identifier: {node_id}",
                    offending_object=node_id,
                    location=f"{location}.node_id",
                )
            )
        node_ids.add(node_id)
    return node_ids


def _validate_edges(
    edges: tuple[dict[str, Any], ...],
    node_ids: set[str],
    diagnostics: list[ValidationDiagnostic],
) -> None:
    edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        location = f"edges[{index}]"
        edge_id = _required_text(edge, "edge_id", location, diagnostics)
        from_node = _required_text(edge, "from_node", location, diagnostics)
        to_node = _required_text(edge, "to_node", location, diagnostics)
        edge_type = _required_text(edge, "edge_type", location, diagnostics)
        _validate_bool(edge, "is_switchable", location, diagnostics)
        _validate_bool(edge, "normally_closed", location, diagnostics)
        _validate_bool(edge, "is_closed", location, diagnostics)
        _validate_number(edge, "rating_kw", location, diagnostics, minimum=0.0)
        _validate_phases(edge.get("phases"), edge_id or location, f"{location}.phases", diagnostics)

        if edge_id:
            if edge_id in edge_ids:
                diagnostics.append(
                    _diagnostic(
                        "duplicate_edge_identifier",
                        f"Duplicate edge identifier: {edge_id}",
                        offending_object=edge_id,
                        location=f"{location}.edge_id",
                    )
                )
            edge_ids.add(edge_id)

        _validate_reference(from_node, node_ids, "from_node", location, diagnostics)
        _validate_reference(to_node, node_ids, "to_node", location, diagnostics)
        if from_node and to_node and from_node == to_node:
            diagnostics.append(
                _diagnostic(
                    "self_loop_edge",
                    f"Edge cannot connect a node to itself: {from_node}",
                    offending_object=edge_id or from_node,
                    location=location,
                )
            )
        if edge_type == "switch" and edge.get("is_switchable") is not True:
            diagnostics.append(
                _diagnostic(
                    "switch_edge_not_switchable",
                    "Edges mapped as switch must be marked switchable",
                    offending_object=edge_id,
                    location=f"{location}.is_switchable",
                )
            )


def _required_text(
    row: dict[str, Any],
    field: str,
    location: str,
    diagnostics: list[ValidationDiagnostic],
) -> str | None:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        diagnostics.append(
            _diagnostic(
                "missing_required_field",
                f"Required field must be a non-empty string: {field}",
                offending_object=str(value) if value is not None else None,
                location=f"{location}.{field}",
            )
        )
        return None
    return value


def _validate_reference(
    value: str | None,
    node_ids: set[str],
    field: str,
    location: str,
    diagnostics: list[ValidationDiagnostic],
) -> None:
    if value and value not in node_ids:
        diagnostics.append(
            _diagnostic(
                "missing_node_reference",
                f"Edge {field} references unknown node: {value}",
                offending_object=value,
                location=f"{location}.{field}",
            )
        )


def _validate_bool(
    row: dict[str, Any],
    field: str,
    location: str,
    diagnostics: list[ValidationDiagnostic],
) -> None:
    if not isinstance(row.get(field), bool):
        diagnostics.append(
            _diagnostic(
                "invalid_boolean",
                f"Field must be boolean: {field}",
                offending_object=str(row.get(field)),
                location=f"{location}.{field}",
            )
        )


def _validate_number(
    row: dict[str, Any],
    field: str,
    location: str,
    diagnostics: list[ValidationDiagnostic],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        diagnostics.append(
            _diagnostic(
                "invalid_number",
                f"Field must be numeric: {field}",
                offending_object=str(value),
                location=f"{location}.{field}",
            )
        )
        return
    if minimum is not None and value < minimum:
        diagnostics.append(
            _diagnostic(
                "number_below_minimum",
                f"Field is below minimum {minimum}: {field}",
                offending_object=str(value),
                location=f"{location}.{field}",
            )
        )
    if maximum is not None and value > maximum:
        diagnostics.append(
            _diagnostic(
                "number_above_maximum",
                f"Field is above maximum {maximum}: {field}",
                offending_object=str(value),
                location=f"{location}.{field}",
            )
        )


def _validate_phases(
    value: Any,
    offending_object: str,
    location: str,
    diagnostics: list[ValidationDiagnostic],
) -> None:
    if not isinstance(value, str) or not value:
        diagnostics.append(
            _diagnostic(
                "invalid_phases",
                "Phases must be a non-empty string containing only A, B, C, or N",
                offending_object=offending_object,
                location=location,
            )
        )
        return
    if any(char not in VALID_PHASES for char in value):
        diagnostics.append(
            _diagnostic(
                "invalid_phases",
                "Phases must contain only A, B, C, or N",
                offending_object=offending_object,
                location=location,
            )
        )


def _diagnostic(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> ValidationDiagnostic:
    return ValidationDiagnostic(
        category=ERROR_CATEGORY_VALIDATION,
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
