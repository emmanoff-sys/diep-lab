"""WP-006-07 Objective 4 ADMS-to-topology mapping tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import (  # noqa: E402
    AdmsTopologyMappingError,
    MappedTopology,
    map_topology,
    transform_identity,
)
from services.adms_topology_import.parser import parse_payload  # noqa: E402


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
                    "external_id": "source node/1",
                    "node_type": "Bus",
                    "name": "Source Node",
                    "latitude": 9.0765,
                    "longitude": 7.3986,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {"region": "abuja", "sequence": 1},
                },
                {
                    "external_id": "source-node-2",
                    "node_type": "Substation",
                    "name": "Source Node 2",
                    "latitude": 9.0768,
                    "longitude": 7.3991,
                    "nominal_kv": 33.0,
                    "phases": "ABC",
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "external_id": "edge/1",
                    "from_node": "source node/1",
                    "to_node": "source-node-2",
                    "edge_type": "Breaker",
                    "is_switchable": True,
                    "normally_closed": True,
                    "is_closed": False,
                    "rating_kw": 1500,
                    "phases": "AB",
                    "metadata": {"asset_class": "switchgear"},
                }
            ],
        },
    }


def _parsed(payload=None):
    return parse_payload(payload or _payload())


def _reason_for(parsed):
    try:
        map_topology(parsed)
    except AdmsTopologyMappingError as exc:
        return exc.reason_code
    return None


def test_maps_parsed_contract_to_internal_topology_shape():
    mapped = map_topology(_parsed())

    assert isinstance(mapped, MappedTopology)
    assert mapped.source_system == "adms-supplier-a"
    assert mapped.external_model_id == "model-a"
    assert mapped.external_model_version == "2026.07.08"
    assert isinstance(mapped.nodes, tuple)
    assert isinstance(mapped.edges, tuple)


def test_maps_node_fields_deterministically():
    node = map_topology(_parsed()).nodes[0]

    assert node["node_id"] == "adms:node:source-node-1"
    assert node["node_type"] == "bus"
    assert node["name"] == "Source Node"
    assert node["latitude"] == 9.0765
    assert node["longitude"] == 7.3986
    assert node["nominal_kv"] == 11.0
    assert node["phases"] == "ABC"


def test_maps_edge_fields_and_references_deterministically():
    edge = map_topology(_parsed()).edges[0]

    assert edge["edge_id"] == "adms:edge:edge-1"
    assert edge["from_node"] == "adms:node:source-node-1"
    assert edge["to_node"] == "adms:node:source-node-2"
    assert edge["edge_type"] == "switch"
    assert edge["is_switchable"] is True
    assert edge["normally_closed"] is True
    assert edge["is_closed"] is False
    assert edge["rating_kw"] == 1500.0
    assert edge["phases"] == "AB"


def test_metadata_is_mapped_to_attrs_with_provenance():
    node_attrs = map_topology(_parsed()).nodes[0]["attrs"]

    assert node_attrs == {
        "source": "adms",
        "source_system": "adms-supplier-a",
        "contract_version": "1.0",
        "correlation_id": "11111111-1111-1111-1111-111111111111",
        "idempotency_key": "import-001",
        "external_model_id": "model-a",
        "external_model_version": "2026.07.08",
        "external_model_created_at": "2026-07-08T00:00:00Z",
        "external_id": "source node/1",
        "metadata": {"region": "abuja", "sequence": 1},
    }


def test_supported_node_type_aliases_map_to_sql_types():
    expected = {
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
    for source, target in expected.items():
        payload = _payload()
        payload["topology"]["nodes"][0]["node_type"] = source
        assert map_topology(_parsed(payload)).nodes[0]["node_type"] == target


def test_supported_edge_type_aliases_map_to_sql_types():
    expected = {
        "line": "line",
        "cable": "line",
        "conductor": "line",
        "switch": "switch",
        "breaker": "switch",
        "transformer": "transformer",
        "tie": "tie",
    }
    for source, target in expected.items():
        payload = _payload()
        payload["topology"]["edges"][0]["edge_type"] = source
        assert map_topology(_parsed(payload)).edges[0]["edge_type"] == target


def test_identity_transformation_is_stable_and_prefixes_object_kind():
    assert transform_identity("node", "  feeder/01 phase A  ") == "adms:node:feeder-01-phase-A"
    assert transform_identity("edge", "E.SUB->FDR") == "adms:edge:E.SUB--FDR"


def test_unsupported_node_type_is_rejected_deterministically():
    payload = _payload()
    payload["topology"]["nodes"][0]["node_type"] = "unsupported"

    assert _reason_for(_parsed(payload)) == "unsupported_node_type"


def test_unsupported_edge_type_is_rejected_deterministically():
    payload = _payload()
    payload["topology"]["edges"][0]["edge_type"] = "unsupported"

    assert _reason_for(_parsed(payload)) == "unsupported_edge_type"


def test_mapping_error_exposes_diagnostic_fields():
    payload = _payload()
    payload["topology"]["edges"][0]["edge_type"] = "unsupported"

    with pytest.raises(AdmsTopologyMappingError) as raised:
        map_topology(_parsed(payload))

    error = raised.value
    assert error.category == "mapping"
    assert error.reason_code == "unsupported_edge_type"
    assert error.description == "Unsupported ADMS edge type for mapping: unsupported"
    assert error.offending_object == "edge/1"
    assert error.location == "edge.edge_type"


def test_mapping_does_not_mutate_or_retain_input_metadata():
    payload = _payload()
    parsed = _parsed(payload)
    mapped = map_topology(parsed)

    payload["topology"]["nodes"][0]["metadata"]["region"] = "changed"

    assert mapped.nodes[0]["attrs"]["metadata"]["region"] == "abuja"
