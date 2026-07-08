"""WP-006-07 Objective 5 topology validation tests."""

from __future__ import annotations

import os
import sys
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import MappedTopology, map_topology  # noqa: E402
from services.adms_topology_import.parser import parse_payload  # noqa: E402
from services.adms_topology_import.validation import (  # noqa: E402
    AdmsTopologyValidationError,
    ensure_valid_topology,
    validate_topology,
)


def _payload():
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": "11111111-1111-1111-1111-111111111111",
        "idempotency_key": "import-001",
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "model-a",
            "model_version": "2026.07.08",
            "created_at": "2026-07-08T00:00:00Z",
        },
        "topology": {
            "nodes": [
                {
                    "external_id": "node-1",
                    "node_type": "bus",
                    "name": "Node 1",
                    "latitude": 9.0765,
                    "longitude": 7.3986,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {},
                },
                {
                    "external_id": "node-2",
                    "node_type": "bus",
                    "name": "Node 2",
                    "latitude": 9.0768,
                    "longitude": 7.3991,
                    "nominal_kv": 11.0,
                    "phases": "ABCN",
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "external_id": "edge-1",
                    "from_node": "node-1",
                    "to_node": "node-2",
                    "edge_type": "line",
                    "is_switchable": False,
                    "normally_closed": True,
                    "is_closed": True,
                    "rating_kw": 1500,
                    "phases": "ABC",
                    "metadata": {},
                }
            ],
        },
    }


def _mapped() -> MappedTopology:
    return map_topology(parse_payload(_payload()))


def _node_with(mapped: MappedTopology, index: int, **changes) -> MappedTopology:
    nodes = list(mapped.nodes)
    nodes[index] = {**nodes[index], **changes}
    return replace(mapped, nodes=tuple(nodes))


def _edge_with(mapped: MappedTopology, index: int, **changes) -> MappedTopology:
    edges = list(mapped.edges)
    edges[index] = {**edges[index], **changes}
    return replace(mapped, edges=tuple(edges))


def _reasons(mapped: MappedTopology) -> list[str]:
    return [diagnostic.reason_code for diagnostic in validate_topology(mapped).diagnostics]


def test_valid_mapped_topology_has_no_diagnostics():
    report = validate_topology(_mapped())

    assert report.is_valid is True
    assert report.diagnostics == ()
    assert ensure_valid_topology(_mapped()) is not None


def test_empty_topology_is_rejected():
    mapped = replace(_mapped(), nodes=(), edges=())

    assert _reasons(mapped) == ["empty_topology"]


def test_duplicate_node_identifier_is_rejected():
    mapped = _mapped()
    duplicate = {**mapped.nodes[1], "node_id": mapped.nodes[0]["node_id"]}
    mapped = replace(mapped, nodes=(mapped.nodes[0], duplicate))

    assert _reasons(mapped) == ["duplicate_node_identifier", "missing_node_reference"]


def test_duplicate_edge_identifier_is_rejected():
    mapped = _mapped()
    duplicate = {**mapped.edges[0]}
    mapped = replace(mapped, edges=(mapped.edges[0], duplicate))

    assert _reasons(mapped) == ["duplicate_edge_identifier"]


def test_missing_edge_from_node_reference_is_rejected():
    mapped = _edge_with(_mapped(), 0, from_node="adms:node:missing")

    assert _reasons(mapped) == ["missing_node_reference"]


def test_missing_edge_to_node_reference_is_rejected():
    mapped = _edge_with(_mapped(), 0, to_node="adms:node:missing")

    assert _reasons(mapped) == ["missing_node_reference"]


def test_self_loop_edge_is_rejected():
    node_id = _mapped().nodes[0]["node_id"]
    mapped = _edge_with(_mapped(), 0, from_node=node_id, to_node=node_id)

    assert "self_loop_edge" in _reasons(mapped)


def test_invalid_node_coordinate_bounds_are_rejected():
    mapped = _node_with(_mapped(), 0, latitude=91.0, longitude=-181.0)

    assert _reasons(mapped) == ["number_above_maximum", "number_below_minimum"]


def test_invalid_nominal_voltage_and_rating_are_rejected():
    mapped = _node_with(_mapped(), 0, nominal_kv=-1.0)
    mapped = _edge_with(mapped, 0, rating_kw=-100.0)

    assert _reasons(mapped) == ["number_below_minimum", "number_below_minimum"]


def test_invalid_phases_are_rejected_for_nodes_and_edges():
    mapped = _node_with(_mapped(), 0, phases="AX")
    mapped = _edge_with(mapped, 0, phases="")

    assert _reasons(mapped) == ["invalid_phases", "invalid_phases"]


def test_switch_edge_must_be_switchable():
    mapped = _edge_with(_mapped(), 0, edge_type="switch", is_switchable=False)

    assert _reasons(mapped) == ["switch_edge_not_switchable"]


def test_required_text_and_boolean_fields_are_checked():
    mapped = _node_with(_mapped(), 0, node_id="")
    mapped = _edge_with(mapped, 0, is_closed="true")

    assert _reasons(mapped) == [
        "missing_required_field",
        "invalid_boolean",
        "missing_node_reference",
    ]


def test_validation_error_exposes_first_diagnostic_and_all_diagnostics():
    mapped = _node_with(_mapped(), 0, latitude=91.0)
    mapped = _edge_with(mapped, 0, rating_kw=-100.0)

    with pytest.raises(AdmsTopologyValidationError) as raised:
        validate_topology(mapped).raise_if_invalid()

    error = raised.value
    assert error.category == "validation"
    assert error.reason_code == "number_above_maximum"
    assert error.description == "Field is above maximum 90.0: latitude"
    assert error.offending_object == "91.0"
    assert error.location == "nodes[0].latitude"
    assert [diagnostic.reason_code for diagnostic in error.diagnostics] == [
        "number_above_maximum",
        "number_below_minimum",
    ]
