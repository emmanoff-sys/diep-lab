"""WP-006-08 Objective 14 ADMS import background worker tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adms_topology_import.persistence import (  # noqa: E402
    InMemoryImportPersistenceRepository,
)
from services.adms_topology_import.publish import (  # noqa: E402
    ESTABLISHED_CONCURRENCY_MODEL,
    TopologyPublishPayload,
    TopologyPublishResult,
)
from services.adms_topology_import.runtime import (  # noqa: E402
    RUNTIME_PIPELINE,
    RuntimeExecutionOptions,
    build_import_coordinator,
    build_runtime_dependencies,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
)
from services.adms_topology_import.worker import (  # noqa: E402
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_RETRY_SCHEDULED,
    WORKER_RUNNING,
    WORKER_STOPPED,
    AdmsImportWorkerError,
    BackgroundImportJob,
    BackgroundImportWorker,
    InMemoryImportJobQueue,
    RetryPolicy,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "worker-import-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        return TopologyPublishResult(
            version=51,
            version_row={"version": 51, "label": payload.label},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


@dataclass
class FlakyCoordinator:
    failures_before_success: int = 1
    calls: int = 0

    def submit(self, request, *, options=None):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError("temporary failure")
        return _coordinator().submit(request, options=options)


def _payload() -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "worker-model-a",
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
        body=json.dumps(_payload()),
    )


def _coordinator():
    return build_import_coordinator(
        build_runtime_dependencies(
            publish_gateway=FakePublishGateway(),
            idempotency_store=InMemoryIdempotencyStore(),
            persistence_repository=InMemoryImportPersistenceRepository(),
        )
    )


def _job(job_id: str = "job-001", key: str = IDEMPOTENCY_KEY) -> BackgroundImportJob:
    return BackgroundImportJob(
        job_id=job_id,
        request=_request(key),
        options=RuntimeExecutionOptions(actor="worker"),
        max_attempts=1,
    )


def test_queue_preserves_fifo_order():
    async def scenario():
        queue = InMemoryImportJobQueue()
        await queue.put(_job("job-1"))
        await queue.put(_job("job-2", key="worker-import-002"))
        first = await queue.get()
        queue.task_done()
        second = await queue.get()
        queue.task_done()
        return first.job_id, second.job_id

    assert asyncio.run(scenario()) == ("job-1", "job-2")


def test_worker_run_once_executes_runtime_job():
    async def scenario():
        worker = BackgroundImportWorker(coordinator=_coordinator())
        await worker.enqueue(_job())
        return await worker.run_once()

    result = asyncio.run(scenario())

    assert result is not None
    assert result.status == JOB_COMPLETED
    assert result.runtime_result is not None
    assert result.runtime_result.steps_completed == RUNTIME_PIPELINE


def test_worker_schedules_retry_and_then_completes_job():
    async def scenario():
        coordinator = FlakyCoordinator(failures_before_success=1)
        worker = BackgroundImportWorker(
            coordinator=coordinator,
            retry_policy=RetryPolicy(max_attempts=2),
        )
        await worker.enqueue(_job(max_attempt_job_id()))
        first = await worker.run_once()
        second = await worker.run_once()
        return coordinator.calls, first, second

    calls, first, second = asyncio.run(scenario())

    assert calls == 2
    assert first is not None
    assert first.status == JOB_RETRY_SCHEDULED
    assert first.diagnostic is not None
    assert first.diagnostic.reason_code == "job_execution_failed"
    assert second is not None
    assert second.status == JOB_COMPLETED


def test_worker_marks_cancelled_job_without_executing_runtime():
    async def scenario():
        coordinator = FlakyCoordinator(failures_before_success=0)
        worker = BackgroundImportWorker(coordinator=coordinator)
        job = _job("job-cancelled")
        await worker.enqueue(job)
        worker.cancel_job(job.job_id)
        result = await worker.run_once()
        return coordinator.calls, result

    calls, result = asyncio.run(scenario())

    assert calls == 0
    assert result is not None
    assert result.status == JOB_CANCELLED
    assert result.diagnostic is not None
    assert result.diagnostic.reason_code == "job_cancelled"


def test_worker_records_failed_job_after_retry_limit():
    async def scenario():
        coordinator = FlakyCoordinator(failures_before_success=99)
        worker = BackgroundImportWorker(
            coordinator=coordinator,
            retry_policy=RetryPolicy(max_attempts=1),
        )
        await worker.enqueue(_job("job-failed"))
        return await worker.run_once()

    result = asyncio.run(scenario())

    assert result is not None
    assert result.status == JOB_FAILED
    assert result.diagnostic is not None
    assert result.diagnostic.reason_code == "job_execution_failed"


def test_worker_lifecycle_start_and_graceful_shutdown():
    async def scenario():
        worker = BackgroundImportWorker(coordinator=_coordinator())
        await worker.start()
        assert worker.status == WORKER_RUNNING
        await worker.enqueue(_job("job-lifecycle"))
        while not worker.results:
            await asyncio.sleep(0)
        await worker.shutdown()
        return worker.status, worker.results

    status, results = asyncio.run(scenario())

    assert status == WORKER_STOPPED
    assert len(results) == 1
    assert results[0].status == JOB_COMPLETED


def test_worker_rejects_duplicate_start():
    async def scenario():
        worker = BackgroundImportWorker(coordinator=_coordinator())
        await worker.start()
        try:
            with pytest.raises(AdmsImportWorkerError) as raised:
                await worker.start()
            return raised.value.reason_code
        finally:
            await worker.shutdown()

    assert asyncio.run(scenario()) == "worker_already_running"


def test_retry_policy_caps_delay():
    policy = RetryPolicy(base_delay_seconds=2.0, max_delay_seconds=3.0)

    assert policy.delay_for_attempt(1) == 2.0
    assert policy.delay_for_attempt(2) == 3.0


def max_attempt_job_id() -> str:
    return "job-retry"
