"""WP-006-07 Objective 7 governed publish integration tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import map_topology  # noqa: E402
from services.adms_topology_import.parser import parse_payload  # noqa: E402
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    AdmsTopologyPublishError,
    TopologyPublishPayload,
    TopologyPublishResult,
    build_publish_payload,
    build_rollback_publish_metadata,
    publish_staged_import,
)
from services.adms_topology_import.staging import (  # noqa: E402
    STATUS_PUBLISHED,
    create_staged_import,
    mark_ready_for_publish,
    request_rollback,
)


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def __init__(self, result: TopologyPublishResult | None = None):
        self.calls: list[tuple[TopologyPublishPayload, str]] = []
        self.result = result or TopologyPublishResult(
            version=9,
            version_row={"version": 9, "label": "published"},
            nodes_written=2,
            edges_written=1,
        )

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        self.calls.append((payload, actor))
        return self.result


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
                    "metadata": {},
                }
            ],
        },
    }


def _ready_staged():
    mapped = map_topology(parse_payload(_payload()))
    return mark_ready_for_publish(create_staged_import(mapped, staging_id="stage-1"))


def _reason_for(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except AdmsTopologyPublishError as exc:
        return exc.reason_code
    return None


def test_build_publish_payload_matches_existing_endpoint_shape():
    payload = build_publish_payload(_ready_staged(), actor="engineer", site_name="Site-A")

    assert payload.label == "adms-adms-supplier-a-model-a-2026.07.08"
    assert payload.description == "ADMS staged import stage-1"
    assert payload.site_name == "Site-A"
    assert len(payload.nodes) == 2
    assert len(payload.edges) == 1
    assert payload.nodes[0]["attrs"]["adms_staging_id"] == "stage-1"
    assert payload.edges[0]["attrs"]["adms_publish_actor"] == "engineer"


def test_publish_staged_import_delegates_to_governed_gateway_once():
    gateway = FakePublishGateway()

    result = publish_staged_import(_ready_staged(), gateway, actor="engineer")

    assert result.published_version == 9
    assert result.staged.status == STATUS_PUBLISHED
    assert result.staged.lifecycle[-1].reason == "published_version:9"
    assert len(gateway.calls) == 1
    payload, actor = gateway.calls[0]
    assert actor == "engineer"
    assert payload.nodes[0]["node_id"] == "adms:node:node-1"


def test_publish_requires_ready_for_publish_state():
    staged = create_staged_import(map_topology(parse_payload(_payload())))

    assert _reason_for(publish_staged_import, staged, FakePublishGateway(), actor="engineer") == (
        "staging_not_ready_for_publish"
    )


def test_publish_requires_established_concurrency_model():
    class BadGateway(FakePublishGateway):
        concurrency_model = "custom-lock"

    assert _reason_for(publish_staged_import, _ready_staged(), BadGateway(), actor="engineer") == (
        "unsupported_concurrency_model"
    )


def test_publish_requires_atomic_gateway():
    class BadGateway(FakePublishGateway):
        atomic = False

    assert _reason_for(publish_staged_import, _ready_staged(), BadGateway(), actor="engineer") == (
        "non_atomic_publish_gateway"
    )


def test_publish_verifies_version_consistency():
    gateway = FakePublishGateway(
        TopologyPublishResult(
            version=0,
            version_row={"version": 0},
            nodes_written=2,
            edges_written=1,
        )
    )

    assert _reason_for(publish_staged_import, _ready_staged(), gateway, actor="engineer") == (
        "invalid_published_version"
    )


def test_publish_verifies_written_counts():
    gateway = FakePublishGateway(
        TopologyPublishResult(
            version=9,
            version_row={"version": 9},
            nodes_written=1,
            edges_written=1,
        )
    )

    assert _reason_for(publish_staged_import, _ready_staged(), gateway, actor="engineer") == (
        "node_write_count_mismatch"
    )


def test_publish_verifies_version_row_matches_version():
    gateway = FakePublishGateway(
        TopologyPublishResult(
            version=9,
            version_row={"version": 8},
            nodes_written=2,
            edges_written=1,
        )
    )

    assert _reason_for(publish_staged_import, _ready_staged(), gateway, actor="engineer") == (
        "version_row_mismatch"
    )


def test_rollback_metadata_requires_rollback_requested_state():
    assert _reason_for(build_rollback_publish_metadata, _ready_staged(), actor="engineer") == (
        "rollback_not_requested"
    )


def test_rollback_metadata_propagates_staging_context():
    staged = request_rollback(_ready_staged(), reason="operator rollback", target_version=4)

    assert build_rollback_publish_metadata(staged, actor="engineer") == {
        "adms_staging_id": "stage-1",
        "adms_rollback_actor": "engineer",
        "adms_rollback_reason": "operator rollback",
        "adms_rollback_target_version": 4,
        "adms_external_model_id": "model-a",
        "adms_external_model_version": "2026.07.08",
    }


def test_publish_error_exposes_diagnostic_fields():
    staged = create_staged_import(map_topology(parse_payload(_payload())), staging_id="stage-1")

    with pytest.raises(AdmsTopologyPublishError) as raised:
        publish_staged_import(staged, FakePublishGateway(), actor="engineer")

    error = raised.value
    assert error.category == "publish"
    assert error.reason_code == "staging_not_ready_for_publish"
    assert error.description == "Staged topology must be ready_for_publish before governed publish"
    assert error.offending_object == "stage-1"
    assert error.location == "status"
