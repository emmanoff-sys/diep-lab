"""WP-006-07 Objective 2 ADMS contract parser tests."""

from __future__ import annotations

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.parser import (  # noqa: E402
    AdmsContractParserError,
    MetadataEntry,
    ParsedAdmsEdge,
    ParsedAdmsNode,
    parse_payload,
)


def _valid_payload():
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
                    "metadata": {"region": "abuja", "source": "adms"},
                },
                {
                    "external_id": "node-2",
                    "node_type": "bus",
                    "name": "Node 2",
                    "latitude": 9.0768,
                    "longitude": 7.3991,
                    "nominal_kv": 11,
                    "phases": "ABC",
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
                    "metadata": {"asset_class": "overhead"},
                }
            ],
        },
    }


def _reason_for(payload):
    try:
        parse_payload(payload)
    except AdmsContractParserError as exc:
        return exc.reason_code
    return None


def test_parses_valid_mapping_into_immutable_contract_model():
    parsed = parse_payload(_valid_payload())

    assert parsed.contract_version == "1.0"
    assert parsed.import_mode == "full_snapshot"
    assert parsed.external_model.model_id == "model-a"
    assert isinstance(parsed.nodes, tuple)
    assert isinstance(parsed.edges, tuple)
    assert isinstance(parsed.nodes[0], ParsedAdmsNode)
    assert isinstance(parsed.edges[0], ParsedAdmsEdge)
    assert parsed.nodes[0].metadata == (
        MetadataEntry("region", "abuja"),
        MetadataEntry("source", "adms"),
    )
    assert parsed.diagnostics == ()


def test_parses_valid_json_text_and_bytes():
    payload = _valid_payload()

    assert parse_payload(json.dumps(payload)).correlation_id == payload["correlation_id"]
    assert parse_payload(json.dumps(payload).encode("utf-8")).idempotency_key == "import-001"


def test_malformed_json_is_rejected_deterministically():
    with pytest.raises(AdmsContractParserError) as raised:
        parse_payload('{"contract_version":')

    assert raised.value.category == "payload"
    assert raised.value.reason_code == "malformed_json"
    assert raised.value.offending_object == "payload"
    assert raised.value.location == "line 1, column 21"


def test_payload_root_must_be_object():
    assert _reason_for("[]") == "document_not_object"


def test_missing_contract_version_is_rejected():
    payload = _valid_payload()
    del payload["contract_version"]

    assert _reason_for(payload) == "missing_required_field"


def test_malformed_contract_version_is_rejected():
    payload = _valid_payload()
    payload["contract_version"] = 1.0

    assert _reason_for(payload) == "expected_string"


def test_unsupported_contract_version_is_rejected():
    payload = _valid_payload()
    payload["contract_version"] = "2.0"

    assert _reason_for(payload) == "unsupported_contract_version"


def test_unsupported_import_mode_is_rejected():
    payload = _valid_payload()
    payload["import_mode"] = "incremental_update"

    assert _reason_for(payload) == "unsupported_import_mode"


def test_missing_external_model_field_is_rejected():
    payload = _valid_payload()
    del payload["external_model"]["model_version"]

    assert _reason_for(payload) == "missing_required_field"


def test_missing_topology_section_is_rejected():
    payload = _valid_payload()
    del payload["topology"]

    assert _reason_for(payload) == "missing_required_field"


def test_malformed_nodes_collection_is_rejected():
    payload = _valid_payload()
    payload["topology"]["nodes"] = {"external_id": "node-1"}

    assert _reason_for(payload) == "expected_collection"


def test_malformed_edge_object_is_rejected():
    payload = _valid_payload()
    payload["topology"]["edges"] = ["not-an-object"]

    assert _reason_for(payload) == "expected_object"


def test_missing_node_mandatory_identifier_is_rejected():
    payload = _valid_payload()
    del payload["topology"]["nodes"][0]["external_id"]

    assert _reason_for(payload) == "missing_required_field"


def test_missing_edge_mandatory_lifecycle_field_is_rejected():
    payload = _valid_payload()
    del payload["topology"]["edges"][0]["is_closed"]

    assert _reason_for(payload) == "missing_required_field"


def test_missing_metadata_is_rejected():
    payload = _valid_payload()
    del payload["topology"]["nodes"][0]["metadata"]

    assert _reason_for(payload) == "missing_required_field"


def test_metadata_must_be_object():
    payload = _valid_payload()
    payload["topology"]["nodes"][0]["metadata"] = []

    assert _reason_for(payload) == "expected_object"


def test_invalid_scalar_field_type_is_rejected():
    payload = _valid_payload()
    payload["topology"]["nodes"][0]["latitude"] = "9.0765"

    assert _reason_for(payload) == "expected_number"


def test_boolean_fields_do_not_accept_strings():
    payload = _valid_payload()
    payload["topology"]["edges"][0]["normally_closed"] = "true"

    assert _reason_for(payload) == "expected_boolean"


def test_duplicate_node_identifiers_are_rejected():
    payload = _valid_payload()
    duplicate = copy.deepcopy(payload["topology"]["nodes"][0])
    payload["topology"]["nodes"].append(duplicate)

    assert _reason_for(payload) == "duplicate_identifier"


def test_duplicate_identifier_across_nodes_and_edges_is_rejected():
    payload = _valid_payload()
    payload["topology"]["edges"][0]["external_id"] = "node-1"

    assert _reason_for(payload) == "duplicate_identifier"


def test_unexpected_topology_collection_is_rejected():
    payload = _valid_payload()
    payload["topology"]["transformers"] = []

    assert _reason_for(payload) == "unexpected_topology_collection"


def test_error_contains_category_reason_description_object_and_location():
    payload = _valid_payload()
    payload["topology"]["edges"][0]["rating_kw"] = None

    with pytest.raises(AdmsContractParserError) as raised:
        parse_payload(payload)

    error = raised.value
    assert error.category == "schema"
    assert error.reason_code == "null_required_field"
    assert error.description == "Required field cannot be null: rating_kw"
    assert error.offending_object == "edge-1"
    assert error.location == "$.topology.edges[0].rating_kw"


def test_parser_does_not_retain_mutable_payload_collections():
    payload = _valid_payload()
    parsed = parse_payload(payload)

    payload["topology"]["nodes"][0]["external_id"] = "changed"
    payload["topology"]["nodes"][0]["metadata"]["region"] = "changed"

    assert parsed.nodes[0].external_id == "node-1"
    assert parsed.nodes[0].metadata[0] == MetadataEntry("region", "abuja")
