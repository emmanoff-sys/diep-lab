"""WP-006-08 Objective 17 ADMS import operational management tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.operations import (  # noqa: E402
    ACTION_CANCEL_JOB,
    ACTION_DISABLE_SCHEDULE,
    ACTION_ENABLE_SCHEDULE,
    ACTION_RECONCILE_SCHEDULER,
    ACTION_TRIGGER_SCHEDULE,
    AdmsImportOperationsError,
    ImportOperationsManager,
)
from services.adms_topology_import.persistence import (  # noqa: E402
    SESSION_STATUS_RECEIVED,
    InMemoryImportPersistenceRepository,
)
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    TopologyPublishPayload,
    TopologyPublishResult,
)
from services.adms_topology_import.runtime import (  # noqa: E402
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
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
    validate_request,
)
from services.adms_topology_import.worker import (  # noqa: E402
    JOB_CANCELLED,
    JOB_COMPLETED,
    BackgroundImportJob,
    BackgroundImportWorker,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "operations-import-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        return TopologyPublishResult(
            version=81,
            version_row={"version": 81, "label": payload.label},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


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
            "model_id": "operations-model-a",
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


def _request(key: str = IDEMPOTENCY_KEY) -> TransportRequest:
    return TransportRequest(
        method="POST",
        scheme="https",
        tls_version="1.2",
        client_certificate_subject="CN=adms-import",
        headers={
            "Authorization": f"Bearer {DEV_BEARER}",
            "Content-Type": "application/json",
            "X-Correlation-ID": CORRELATION_ID,
            "Idempotency-Key": key,
        },
        body=json.dumps(_payload(key)),
    )


def _worker(
    repository: InMemoryImportPersistenceRepository | None = None,
) -> BackgroundImportWorker:
    coordinator = build_import_coordinator(
        build_runtime_dependencies(
            publish_gateway=FakePublishGateway(),
            idempotency_store=InMemoryIdempotencyStore(),
            persistence_repository=repository or InMemoryImportPersistenceRepository(),
        )
    )
    return BackgroundImportWorker(coordinator=coordinator)


def _schedule(
    *,
    schedule_id: str = "schedule-ops-001",
    starts_at: datetime | None = None,
    key: str = IDEMPOTENCY_KEY,
) -> ScheduledImport:
    return ScheduledImport(
        schedule_id=schedule_id,
        request=_request(key),
        recurrence=RecurringExecutionPolicy(interval_seconds=60, starts_at=starts_at),
        options=RuntimeExecutionOptions(actor="operations"),
        execution_window=ExecutionWindow(),
        max_attempts=1,
    )


def _seed_session(repository: InMemoryImportPersistenceRepository) -> str:
    transport = validate_request(_request(), idempotency_store=InMemoryIdempotencyStore())
    session = repository.create_import_session(transport, actor="operator")
    repository.append_history(
        session.session_id,
        step="transport",
        status=SESSION_STATUS_RECEIVED,
        reason="seeded_for_operations_test",
    )
    repository.record_checkpoint(
        session.session_id,
        step="transport",
        data={"correlation_id": transport.correlation_id},
    )
    return session.session_id


def test_metrics_snapshot_counts_repository_worker_and_scheduler_state():
    async def scenario():
        repository = InMemoryImportPersistenceRepository()
        _seed_session(repository)
        worker = _worker(repository)
        clock = Clock(datetime(2026, 7, 8, 12, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(_schedule(starts_at=clock.now(), key="operations-scheduled-001"))
        await scheduler.tick()
        await worker.run_once()
        scheduler.reconcile_worker_results()
        manager = ImportOperationsManager(
            repository=repository,
            worker=worker,
            scheduler=scheduler,
        )
        return manager.metrics_snapshot()

    snapshot = asyncio.run(scenario())

    assert snapshot.session_count == 2
    assert snapshot.history_count >= 1
    assert snapshot.checkpoint_count >= 1
    assert snapshot.worker_result_count == 1
    assert snapshot.scheduler_execution_count == 1
    assert snapshot.sessions_by_status["received"] == 1
    assert snapshot.sessions_by_status["published"] == 1
    assert snapshot.worker_results_by_status[JOB_COMPLETED] == 1


def test_diagnostics_report_runtime_component_status_without_mutation():
    repository = InMemoryImportPersistenceRepository()
    worker = _worker(repository)
    scheduler = ImportScheduler(worker=worker)
    manager = ImportOperationsManager(
        repository=repository,
        worker=worker,
        scheduler=scheduler,
    )

    diagnostics = manager.diagnostics()

    assert diagnostics.repository_session_count == 0
    assert diagnostics.worker_status == "stopped"
    assert diagnostics.scheduler_status == "stopped"
    assert diagnostics.worker_result_count == 0
    assert diagnostics.scheduler_execution_count == 0


def test_execution_report_returns_session_history_and_checkpoints():
    repository = InMemoryImportPersistenceRepository()
    session_id = _seed_session(repository)
    manager = ImportOperationsManager(repository=repository)

    report = manager.execution_report(session_id)

    assert report.session.session_id == session_id
    assert report.session.status == SESSION_STATUS_RECEIVED
    assert [record.step for record in report.history] == ["transport"]
    assert [record.step for record in report.checkpoints] == ["transport"]


def test_execution_report_rejects_unknown_session_deterministically():
    manager = ImportOperationsManager(repository=InMemoryImportPersistenceRepository())

    with pytest.raises(AdmsImportOperationsError) as raised:
        manager.execution_report("missing-session")

    assert raised.value.reason_code == "unknown_import_session"


def test_operator_cancel_control_delegates_to_background_worker():
    async def scenario():
        worker = _worker()
        manager = ImportOperationsManager(
            repository=InMemoryImportPersistenceRepository(),
            worker=worker,
        )
        job = BackgroundImportJob(job_id="job-ops-cancel", request=_request())
        await worker.enqueue(job)
        action = manager.cancel_background_job(job.job_id)
        result = await worker.run_once()
        return action, result

    action, result = asyncio.run(scenario())

    assert action.action == ACTION_CANCEL_JOB
    assert action.status == "accepted"
    assert result is not None
    assert result.status == JOB_CANCELLED


def test_operator_schedule_trigger_and_reconcile_use_scheduler_hooks():
    async def scenario():
        repository = InMemoryImportPersistenceRepository()
        worker = _worker(repository)
        scheduler = ImportScheduler(worker=worker)
        scheduler.add_schedule(_schedule(key="operations-trigger-001"))
        manager = ImportOperationsManager(
            repository=repository,
            worker=worker,
            scheduler=scheduler,
        )
        trigger = await manager.trigger_schedule("schedule-ops-001")
        result = await worker.run_once()
        reconcile = manager.reconcile_scheduler()
        return trigger, result, reconcile, scheduler.executions

    trigger, result, reconcile, executions = asyncio.run(scenario())

    assert trigger.action == ACTION_TRIGGER_SCHEDULE
    assert trigger.target == "schedule-ops-001:1"
    assert result is not None
    assert result.status == JOB_COMPLETED
    assert reconcile.action == ACTION_RECONCILE_SCHEDULER
    assert len(executions) == 1


def test_operator_can_disable_and_enable_schedule_without_changing_definition():
    repository = InMemoryImportPersistenceRepository()
    worker = _worker(repository)
    scheduler = ImportScheduler(worker=worker)
    scheduler.add_schedule(_schedule())
    manager = ImportOperationsManager(
        repository=repository,
        worker=worker,
        scheduler=scheduler,
    )

    disabled = manager.disable_schedule("schedule-ops-001")
    assert disabled.action == ACTION_DISABLE_SCHEDULE
    assert not scheduler.get_schedule("schedule-ops-001").enabled

    enabled = manager.enable_schedule("schedule-ops-001")
    assert enabled.action == ACTION_ENABLE_SCHEDULE
    assert scheduler.get_schedule("schedule-ops-001").enabled


def test_operator_actions_require_configured_components():
    manager = ImportOperationsManager(repository=InMemoryImportPersistenceRepository())

    with pytest.raises(AdmsImportOperationsError) as worker_error:
        manager.cancel_background_job("job-missing")
    with pytest.raises(AdmsImportOperationsError) as scheduler_error:
        manager.reconcile_scheduler()

    assert worker_error.value.reason_code == "worker_unavailable"
    assert scheduler_error.value.reason_code == "scheduler_unavailable"
