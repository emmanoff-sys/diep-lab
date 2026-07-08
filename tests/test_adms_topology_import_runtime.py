"""WP-006-08 Objective 11 ADMS import runtime orchestration tests."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import import build_runtime_coordinator  # noqa: E402
from services.adms_topology_import.parser import AdmsContractParserError  # noqa: E402
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    TopologyPublishPayload,
    TopologyPublishResult,
)
from services.adms_topology_import.runtime import (  # noqa: E402
    RUNTIME_PIPELINE,
    STATUS_PUBLISHED,
    STATUS_REPLAYED,
    AdmsImportRuntimeError,
    RuntimeExecutionOptions,
    build_import_coordinator,
    build_runtime_dependencies,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    TransportValidationError,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "runtime-import-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def __init__(self) -> None:
        self.calls: list[tuple[TopologyPublishPayload, str]] = []

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        self.calls.append((payload, actor))
        return TopologyPublishResult(
            version=21,
            version_row={"version": 21, "label": payload.label},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


def _payload() -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "runtime-model-a",
            "model_version": "2026.07.08",
            "created_at": "2026-07-08T00:00:00Z",
        },
        "topology": {
            "nodes": [
                {
                    "external_id": "source-1",
                    "node_type": "substation",
                    "name": "Source 1",
                    "latitude": 9.0765,
                    "longitude": 7.3986,
                    "nominal_kv": 33.0,
                    "phases": "ABC",
                    "metadata": {},
                },
                {
                    "external_id": "load-1",
                    "node_type": "load",
                    "name": "Load 1",
                    "latitude": 9.0770,
                    "longitude": 7.3990,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "external_id": "edge-1",
                    "from_node": "source-1",
                    "to_node": "load-1",
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


def _request(payload: dict | None = None, **overrides) -> TransportRequest:
    headers = {
        "Authorization": f"Bearer {DEV_BEARER}",
        "Content-Type": "application/json",
        "X-Correlation-ID": CORRELATION_ID,
        "Idempotency-Key": IDEMPOTENCY_KEY,
    }
    headers.update(overrides.pop("headers", {}))
    values = {
        "method": "POST",
        "scheme": "https",
        "tls_version": "1.2",
        "client_certificate_subject": "CN=adms-import",
        "headers": headers,
        "body": json.dumps(payload or _payload()),
    }
    values.update(overrides)
    return TransportRequest(**values)


def test_runtime_coordinator_executes_authorised_pipeline_in_order():
    gateway = FakePublishGateway()
    dependencies = build_runtime_dependencies(
        publish_gateway=gateway,
        idempotency_store=InMemoryIdempotencyStore(),
    )
    coordinator = build_import_coordinator(dependencies)

    result = coordinator.submit(
        _request(),
        options=RuntimeExecutionOptions(
            actor="runtime-operator",
            site_name="Runtime Site",
            staging_id="stage-runtime-001",
        ),
    )

    assert coordinator.controller.pipeline == RUNTIME_PIPELINE
    assert result.status == STATUS_PUBLISHED
    assert result.steps_completed == RUNTIME_PIPELINE
    assert result.transport.replay is False
    assert result.parsed is not None
    assert result.mapped is not None
    assert result.staged is not None
    assert result.published is not None
    assert result.published.published_version == 21
    assert result.correlation.staging_id == "stage-runtime-001"
    assert result.log_events[0]["event"] == "adms.import.published"
    assert result.audit_events[0].event_type == "adms.topology_import.published"
    payload, actor = gateway.calls[0]
    assert actor == "runtime-operator"
    assert payload.site_name == "Runtime Site"
    assert payload.nodes[0]["node_id"] == "adms:node:source-1"


def test_container_builds_runtime_coordinator_with_injected_dependencies():
    gateway = FakePublishGateway()
    store = InMemoryIdempotencyStore()

    coordinator = build_runtime_coordinator(publish_gateway=gateway, idempotency_store=store)

    result = coordinator.submit(_request(), options=RuntimeExecutionOptions(actor="operator"))

    assert result.status == STATUS_PUBLISHED
    assert gateway.calls[0][1] == "operator"


def test_runtime_replay_stops_before_parse_map_stage_and_publish():
    gateway = FakePublishGateway()
    store = InMemoryIdempotencyStore()
    coordinator = build_import_coordinator(
        build_runtime_dependencies(publish_gateway=gateway, idempotency_store=store)
    )

    first = coordinator.submit(_request())
    second = coordinator.submit(_request())

    assert first.status == STATUS_PUBLISHED
    assert second.status == STATUS_REPLAYED
    assert second.steps_completed == ("transport", "replay")
    assert second.parsed is None
    assert second.published is None
    assert second.log_events[0]["event"] == "adms.import.replayed"
    assert len(gateway.calls) == 1


def test_runtime_requires_injected_publish_gateway():
    coordinator = build_import_coordinator(build_runtime_dependencies())

    with pytest.raises(AdmsImportRuntimeError) as raised:
        coordinator.submit(_request())

    assert raised.value.category == "runtime"
    assert raised.value.reason_code == "missing_publish_gateway"
    assert raised.value.location == "dependencies.publish_gateway"


def test_runtime_preserves_transport_error_boundary():
    coordinator = build_import_coordinator(
        build_runtime_dependencies(publish_gateway=FakePublishGateway())
    )

    with pytest.raises(TransportValidationError) as raised:
        coordinator.submit(_request(headers={"Authorization": "Bearer wrong-token"}))

    assert raised.value.reason_code == "invalid_bearer_token"
    assert raised.value.location == "headers.Authorization"


def test_runtime_preserves_parser_error_boundary_after_transport():
    gateway = FakePublishGateway()
    coordinator = build_import_coordinator(build_runtime_dependencies(publish_gateway=gateway))
    payload = _payload()
    payload["contract_version"] = "2.0"

    with pytest.raises(AdmsContractParserError) as raised:
        coordinator.submit(_request(payload))

    assert raised.value.reason_code == "unsupported_contract_version"
    assert gateway.calls == []
