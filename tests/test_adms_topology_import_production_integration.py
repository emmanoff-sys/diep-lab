"""WP-006-08 Objective 19 production ADMS runtime integration tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.api import create_runtime_router  # noqa: E402
from services.adms_topology_import.operations import ImportOperationsManager  # noqa: E402
from services.adms_topology_import.persistence import (  # noqa: E402
    SESSION_STATUS_MAPPED,
    SESSION_STATUS_PUBLISHED,
    SESSION_STATUS_RECEIVED,
    SESSION_STATUS_RETRY_REQUESTED,
    InMemoryImportPersistenceRepository,
)
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    TopologyPublishPayload,
    TopologyPublishResult,
)
from services.adms_topology_import.recovery import (  # noqa: E402
    FailureRecoveryCoordinator,
    RecoveryRetryPolicy,
)
from services.adms_topology_import.runtime import (  # noqa: E402
    RUNTIME_PIPELINE,
    RuntimeExecutionOptions,
    build_import_coordinator,
    build_runtime_dependencies,
)
from services.adms_topology_import.scheduler import (  # noqa: E402
    ExecutionWindow,
    ImportScheduler,
    RecurringExecutionPolicy,
    ScheduledImport,
)
from services.adms_topology_import.security import (  # noqa: E402
    PERMISSION_ADMIN,
    InMemorySecurityAuditRecorder,
    RuntimeCredentialStore,
    RuntimeSecurityConfig,
    RuntimeSecurityPolicy,
    StaticSecretProvider,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    validate_request,
)
from services.adms_topology_import.worker import (  # noqa: E402
    JOB_COMPLETED,
    JOB_FAILED,
    BackgroundImportJob,
    BackgroundImportWorker,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "production-integration-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def __init__(self, *, version: int = 91, fail: bool = False) -> None:
        self.version = version
        self.fail = fail
        self.calls: list[tuple[TopologyPublishPayload, str]] = []

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        self.calls.append((payload, actor))
        if self.fail:
            raise RuntimeError("publish unavailable")
        return TopologyPublishResult(
            version=self.version,
            version_row={"version": self.version, "label": payload.label},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


@dataclass
class IntegrationRuntime:
    repository: InMemoryImportPersistenceRepository
    idempotency_store: InMemoryIdempotencyStore
    gateway: FakePublishGateway
    audit: InMemorySecurityAuditRecorder
    policy: RuntimeSecurityPolicy


@dataclass
class Clock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def _payload(key: str = IDEMPOTENCY_KEY) -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": key,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "production-runtime-model",
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
                    "metadata": {"region": "abuja"},
                },
                {
                    "external_id": "load-1",
                    "node_type": "load",
                    "name": "Load 1",
                    "latitude": 9.0770,
                    "longitude": 7.3990,
                    "nominal_kv": 11.0,
                    "phases": "ABC",
                    "metadata": {"source": "adms"},
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
                    "metadata": {"asset_class": "overhead"},
                }
            ],
        },
    }


def _headers(
    *,
    token: str = DEV_BEARER,
    key: str = IDEMPOTENCY_KEY,
    correlation_id: str = CORRELATION_ID,
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
        "Idempotency-Key": key,
        "X-TLS-Version": "1.2",
        "X-Client-Certificate-Subject": "CN=adms-import",
    }


def _transport(key: str = IDEMPOTENCY_KEY) -> TransportRequest:
    return TransportRequest(
        method="POST",
        scheme="https",
        tls_version="1.2",
        client_certificate_subject="CN=adms-import",
        headers=_headers(key=key),
        body=json.dumps(_payload(key)),
    )


def _runtime(*, gateway: FakePublishGateway | None = None) -> IntegrationRuntime:
    audit = InMemorySecurityAuditRecorder()
    store = RuntimeCredentialStore(
        secret_provider=StaticSecretProvider({"ADMS_IMPORT_OPERATOR_TOKEN": DEV_BEARER}),
        credential_secrets={"operator": "ADMS_IMPORT_OPERATOR_TOKEN"},
        permissions={"operator": {PERMISSION_ADMIN}},
        certificate_subjects={"operator": "CN=adms-import"},
    )
    return IntegrationRuntime(
        repository=InMemoryImportPersistenceRepository(),
        idempotency_store=InMemoryIdempotencyStore(),
        gateway=gateway or FakePublishGateway(),
        audit=audit,
        policy=RuntimeSecurityPolicy(
            credential_store=store,
            config=RuntimeSecurityConfig(
                require_tls=True,
                min_tls_version="1.2",
                require_client_certificate=True,
                require_audit=True,
            ),
            audit_recorder=audit,
        ),
    )


def _coordinator(runtime: IntegrationRuntime):
    return build_import_coordinator(
        build_runtime_dependencies(
            publish_gateway=runtime.gateway,
            idempotency_store=runtime.idempotency_store,
            persistence_repository=runtime.repository,
        )
    )


def _app(runtime: IntegrationRuntime) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_runtime_router(
            coordinator=_coordinator(runtime),
            repository=runtime.repository,
            security_policy=runtime.policy,
        )
    )
    return app


def _schedule(
    key: str,
    request: TransportRequest,
    starts_at: datetime,
) -> ScheduledImport:
    return ScheduledImport(
        schedule_id="prod-schedule-001",
        request=request,
        recurrence=RecurringExecutionPolicy(interval_seconds=60, starts_at=starts_at),
        options=RuntimeExecutionOptions(actor="production-scheduler"),
        execution_window=ExecutionWindow(),
        max_attempts=1,
    )


def _seed_recoverable_session(repository: InMemoryImportPersistenceRepository) -> str:
    transport = validate_request(
        _transport("production-recovery-001"),
        idempotency_store=InMemoryIdempotencyStore(),
    )
    session = repository.create_import_session(transport, actor="operator")
    repository.append_history(
        session.session_id,
        step="transport",
        status=SESSION_STATUS_RECEIVED,
        reason="transport_validated",
    )
    repository.record_checkpoint(
        session.session_id,
        step="transport",
        data={"payload_sha256": transport.payload_sha256},
    )
    repository.update_import_session(session.session_id, status=SESSION_STATUS_MAPPED)
    repository.append_history(
        session.session_id,
        step="map",
        status=SESSION_STATUS_MAPPED,
        reason="topology_mapped",
    )
    repository.record_checkpoint(
        session.session_id,
        step="map",
        data={"node_count": 2, "edge_count": 1},
    )
    return session.session_id


def test_production_runtime_api_executes_secure_import_and_reports_operational_state():
    runtime = _runtime()
    client = TestClient(_app(runtime), base_url="https://testserver")

    response = client.post(
        "/adms/topology-imports",
        json={
            "payload": _payload(),
            "actor": "operator",
            "staging_id": "stage-production-001",
        },
        headers=_headers(),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == SESSION_STATUS_PUBLISHED
    assert body["published_version"] == 91
    assert body["steps_completed"] == list(RUNTIME_PIPELINE)
    assert runtime.gateway.calls[0][1] == "operator"
    assert runtime.audit.events[-1].operation == "submit_import"

    manager = ImportOperationsManager(repository=runtime.repository)
    report = manager.execution_report(body["session_id"])
    snapshot = manager.metrics_snapshot()

    assert report.session.status == SESSION_STATUS_PUBLISHED
    assert [record.step for record in report.history] == list(RUNTIME_PIPELINE)
    assert [record.step for record in report.checkpoints] == list(RUNTIME_PIPELINE)
    assert snapshot.sessions_by_status[SESSION_STATUS_PUBLISHED] == 1


def test_invalid_runtime_import_rolls_back_persistence_and_propagates_error():
    runtime = _runtime()
    payload = _payload("production-invalid-001")
    payload["topology"]["edges"][0]["to_node"] = "missing-node"
    client = TestClient(_app(runtime), base_url="https://testserver")

    response = client.post(
        "/adms/topology-imports",
        json={"payload": payload, "actor": "operator"},
        headers=_headers(key="production-invalid-001"),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "missing_node_reference"
    assert runtime.repository.list_import_sessions() == ()
    assert runtime.gateway.calls == []


def test_worker_scheduler_operations_and_idempotency_integrate_deterministically():
    async def scenario():
        runtime = _runtime()
        worker = BackgroundImportWorker(coordinator=_coordinator(runtime))
        clock = Clock(datetime(2026, 7, 8, 13, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(
            _schedule(
                "production-scheduled-001", _transport("production-scheduled-001"), clock.now()
            )
        )
        manager = ImportOperationsManager(
            repository=runtime.repository,
            worker=worker,
            scheduler=scheduler,
        )

        records = await scheduler.tick()
        blocked = await scheduler.tick()
        first = await worker.run_once()
        manager.reconcile_scheduler()
        await worker.enqueue(
            BackgroundImportJob(
                job_id="prod-replay",
                request=_transport("production-scheduled-001"),
                options=RuntimeExecutionOptions(actor="production-scheduler"),
            )
        )
        replay = await worker.run_once()
        return records, blocked, first, replay, manager.metrics_snapshot()

    records, blocked, first, replay, snapshot = asyncio.run(scenario())

    assert len(records) == 1
    assert blocked == ()
    assert first is not None
    assert first.status == JOB_COMPLETED
    assert first.runtime_result is not None
    assert first.runtime_result.status == SESSION_STATUS_PUBLISHED
    assert replay is not None
    assert replay.status == JOB_COMPLETED
    assert replay.runtime_result is not None
    assert replay.runtime_result.status == "replayed"
    assert snapshot.worker_results_by_status[JOB_COMPLETED] == 2
    assert snapshot.scheduler_execution_count == 1


def test_runtime_cancellation_and_retry_controls_update_persistent_history():
    runtime = _runtime()
    client = TestClient(_app(runtime), base_url="https://testserver")
    transport = validate_request(_transport("production-control-001"))
    session = runtime.repository.create_import_session(transport, actor="operator")

    cancel = client.post(
        f"/adms/topology-imports/{session.session_id}/cancel",
        headers=_headers(key="production-control-001"),
    )

    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    second_transport = validate_request(_transport("production-control-002"))
    second = runtime.repository.create_import_session(second_transport, actor="operator")
    retry = client.post(
        f"/adms/topology-imports/{second.session_id}/retry",
        json={"reason": "operator_retry"},
        headers=_headers(key="production-control-002"),
    )

    assert retry.status_code == 200
    assert retry.json()["status"] == SESSION_STATUS_RETRY_REQUESTED
    assert runtime.repository.history_for_session(session.session_id)[-1].step == "cancel"
    assert runtime.repository.history_for_session(second.session_id)[-1].step == "retry"


def test_failure_recovery_coordinates_retry_and_checkpoint_rollback_integrity():
    runtime = _runtime()
    session_id = _seed_recoverable_session(runtime.repository)
    recovery = FailureRecoveryCoordinator(
        repository=runtime.repository,
        retry_policy=RecoveryRetryPolicy(max_attempts=2),
    )

    initial_diagnostics = recovery.diagnostics(session_id)
    rollback = recovery.rollback_to_latest_checkpoint(session_id)
    retry = recovery.request_retry(
        session_id,
        attempt=1,
        reason_code="job_execution_failed",
    )
    retry_diagnostics = recovery.diagnostics(session_id)

    assert initial_diagnostics.latest_checkpoint_step == "map"
    assert initial_diagnostics.restorable
    assert rollback.restored_status == SESSION_STATUS_MAPPED
    assert rollback.recovery_checkpoint.data["restored_status"] == SESSION_STATUS_MAPPED
    assert retry.decision.retry_allowed
    assert retry.session.status == SESSION_STATUS_RETRY_REQUESTED
    assert retry_diagnostics.latest_checkpoint_step == "recovery"
    assert retry_diagnostics.restorable is False
    assert (
        runtime.repository.get_import_session(session_id).status == SESSION_STATUS_RETRY_REQUESTED
    )


def test_worker_failure_preserves_error_state_without_partial_persistence():
    async def scenario():
        runtime = _runtime(gateway=FakePublishGateway(fail=True))
        worker = BackgroundImportWorker(coordinator=_coordinator(runtime))
        await worker.enqueue(
            BackgroundImportJob(
                job_id="prod-failure",
                request=_transport("production-failure-001"),
                options=RuntimeExecutionOptions(actor="production-worker"),
            )
        )
        result = await worker.run_once()
        manager = ImportOperationsManager(repository=runtime.repository, worker=worker)
        return result, manager.metrics_snapshot()

    result, snapshot = asyncio.run(scenario())

    assert result is not None
    assert result.status == JOB_FAILED
    assert result.diagnostic is not None
    assert result.diagnostic.reason_code == "job_execution_failed"
    assert snapshot.session_count == 0
    assert snapshot.worker_results_by_status[JOB_FAILED] == 1
