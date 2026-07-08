"""WP-006-07 Objective 9 ADMS topology import compatibility tests."""

from __future__ import annotations

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.mapping import map_topology  # noqa: E402
from services.adms_topology_import.metrics import AdmsImportMetrics  # noqa: E402
from services.adms_topology_import.observability import (  # noqa: E402
    audit_lifecycle_event,
    correlation_for_staged,
    correlation_from_transport,
    deterministic_audit_event_id,
    record_lifecycle_metrics,
    record_validation_metrics,
    structured_log_event,
)
from services.adms_topology_import.parser import (  # noqa: E402
    AdmsContractParserError,
    parse_payload,
)
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    AdmsTopologyPublishError,
    TopologyPublishPayload,
    TopologyPublishResult,
    publish_staged_import,
)
from services.adms_topology_import.staging import (  # noqa: E402
    STATUS_PUBLISHED,
    create_staged_import,
    mark_ready_for_publish,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    TransportValidationError,
    validate_request,
)
from services.adms_topology_import.validation import (  # noqa: E402
    AdmsTopologyValidationError,
    ensure_valid_topology,
    validate_topology,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "import-compat-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def __init__(self, result: TopologyPublishResult | None = None) -> None:
        self.calls: list[tuple[TopologyPublishPayload, str]] = []
        self.result = result or TopologyPublishResult(
            version=11,
            version_row={"version": 11, "label": "published"},
            nodes_written=2,
            edges_written=1,
        )

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        self.calls.append((payload, actor))
        return self.result


def _payload() -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "feeder-model-a",
            "model_version": "2026.07.08",
            "created_at": "2026-07-08T00:00:00Z",
        },
        "topology": {
            "nodes": [
                {
                    "external_id": "substation-1",
                    "node_type": "substation",
                    "name": "Substation 1",
                    "latitude": 9.0765,
                    "longitude": 7.3986,
                    "nominal_kv": 33.0,
                    "phases": "ABC",
                    "metadata": {"region": "abuja"},
                },
                {
                    "external_id": "feeder-1",
                    "node_type": "feeder",
                    "name": "Feeder 1",
                    "latitude": 9.0770,
                    "longitude": 7.3990,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {"source": "adms"},
                },
            ],
            "edges": [
                {
                    "external_id": "line-1",
                    "from_node": "substation-1",
                    "to_node": "feeder-1",
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


def _request(payload: dict | bytes | str | None = None, **overrides) -> TransportRequest:
    body = payload if isinstance(payload, bytes | str) else json.dumps(payload or _payload())
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
        "body": body,
    }
    values.update(overrides)
    return TransportRequest(**values)


def _ready_staged_from_body(body: bytes | str, *, actor: str = "compatibility-test"):
    parsed = parse_payload(body)
    mapped = ensure_valid_topology(map_topology(parsed))
    staged = create_staged_import(mapped, staging_id="stage-compat-001", actor=actor)
    return mark_ready_for_publish(staged, actor=actor)


def test_complete_positive_pipeline_is_contract_compatible():
    store = InMemoryIdempotencyStore()
    transport = validate_request(_request(), idempotency_store=store)
    transport_context = correlation_from_transport(transport)
    staged = _ready_staged_from_body(transport.body)
    staged_context = correlation_for_staged(
        staged,
        correlation_id=transport_context.correlation_id,
        idempotency_key=transport_context.idempotency_key,
    )
    gateway = FakePublishGateway()

    published = publish_staged_import(
        staged,
        gateway,
        actor="compatibility-test",
        site_name="Compatibility Site",
    )
    log_event = structured_log_event(
        "adms.import.published",
        context=staged_context,
        status=published.staged.status,
        published_version=published.published_version,
    )
    audit_event = audit_lifecycle_event(
        published.staged,
        correlation_id=transport.correlation_id,
        action="topology_import.publish",
    )

    assert transport.replay is False
    assert published.published_version == 11
    assert published.staged.status == STATUS_PUBLISHED
    assert len(gateway.calls) == 1
    payload, actor = gateway.calls[0]
    assert actor == "compatibility-test"
    assert payload.label == "adms-adms-supplier-a-feeder-model-a-2026.07.08"
    assert payload.site_name == "Compatibility Site"
    assert payload.nodes[0]["node_id"] == "adms:node:substation-1"
    assert payload.edges[0]["from_node"] == "adms:node:substation-1"
    assert payload.edges[0]["attrs"]["adms_staging_id"] == "stage-compat-001"
    assert log_event["correlation_id"] == CORRELATION_ID
    assert log_event["idempotency_key"] == IDEMPOTENCY_KEY
    assert audit_event.event_type == "adms.topology_import.published"
    assert audit_event.metadata["node_count"] == 2
    assert deterministic_audit_event_id(audit_event) == deterministic_audit_event_id(audit_event)


def test_replay_request_is_detected_before_pipeline_reexecution():
    store = InMemoryIdempotencyStore()
    first = validate_request(_request(), idempotency_store=store)
    second = validate_request(_request(), idempotency_store=store)
    gateway = FakePublishGateway()

    if not first.replay:
        publish_staged_import(
            _ready_staged_from_body(first.body), gateway, actor="compatibility-test"
        )
    if not second.replay:
        publish_staged_import(
            _ready_staged_from_body(second.body),
            gateway,
            actor="compatibility-test",
        )

    assert first.replay is False
    assert second.replay is True
    assert len(gateway.calls) == 1


def test_transport_rejection_prevents_payload_processing():
    with pytest.raises(TransportValidationError) as raised:
        validate_request(_request(headers={"Authorization": "Bearer wrong-token"}))

    assert raised.value.reason_code == "invalid_bearer_token"
    assert raised.value.location == "headers.Authorization"


def test_contract_parser_failure_propagates_before_mapping():
    payload = _payload()
    payload["contract_version"] = "2.0"
    request = _request(payload)
    transport = validate_request(request)

    with pytest.raises(AdmsContractParserError) as raised:
        parse_payload(transport.body)

    assert raised.value.reason_code == "unsupported_contract_version"
    assert raised.value.location == "$.contract_version"


def test_validation_failure_blocks_staging_and_publish():
    payload = _payload()
    payload["topology"]["edges"][0]["to_node"] = "missing-node"
    mapped = map_topology(parse_payload(payload))
    report = validate_topology(mapped)

    with pytest.raises(AdmsTopologyValidationError) as raised:
        report.raise_if_invalid()

    assert raised.value.reason_code == "missing_node_reference"
    assert raised.value.location == "edges[0].to_node"


def test_publish_error_propagates_deterministically_after_staging():
    staged = _ready_staged_from_body(json.dumps(_payload()))
    gateway = FakePublishGateway(
        TopologyPublishResult(
            version=11,
            version_row={"version": 11},
            nodes_written=2,
            edges_written=0,
        )
    )

    with pytest.raises(AdmsTopologyPublishError) as raised:
        publish_staged_import(staged, gateway, actor="compatibility-test")

    assert raised.value.reason_code == "edge_write_count_mismatch"
    assert raised.value.location == "publish_result.edges_written"


def test_contract_compatibility_rejects_conflicting_idempotency_reuse():
    store = InMemoryIdempotencyStore()
    validate_request(_request(), idempotency_store=store)
    changed_payload = _payload()
    changed_payload["external_model"]["model_version"] = "2026.07.09"

    with pytest.raises(TransportValidationError) as raised:
        validate_request(_request(changed_payload), idempotency_store=store)

    assert raised.value.reason_code == "idempotency_key_conflict"
    assert raised.value.offending_object == IDEMPOTENCY_KEY
    assert raised.value.location == "headers.Idempotency-Key"


def test_observability_recorders_do_not_change_pipeline_outcomes():
    mapped = map_topology(parse_payload(_payload()))
    invalid = copy.deepcopy(mapped)
    invalid.nodes[0]["latitude"] = 91.0
    report = validate_topology(invalid)
    metrics = AdmsImportMetrics(enabled=False)

    record_lifecycle_metrics(metrics, status="staged")
    record_validation_metrics(metrics, report)

    assert report.is_valid is False
    assert report.diagnostics[0].reason_code == "number_above_maximum"
    assert ensure_valid_topology(mapped) is mapped
