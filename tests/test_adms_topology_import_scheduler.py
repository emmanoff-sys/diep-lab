"""WP-006-08 Objective 15 ADMS import scheduler tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
from services.adms_topology_import.scheduler import (  # noqa: E402
    SCHEDULER_RUNNING,
    SCHEDULER_STOPPED,
    TRIGGER_REASON_MANUAL,
    TRIGGER_REASON_SCHEDULED,
    AdmsImportSchedulerError,
    ExecutionWindow,
    ImportScheduler,
    RecurringExecutionPolicy,
    ScheduledImport,
    SchedulerConfig,
    disable_schedule,
)
from services.adms_topology_import.transport import (  # noqa: E402
    InMemoryIdempotencyStore,
    TransportRequest,
)
from services.adms_topology_import.worker import (  # noqa: E402
    JOB_COMPLETED,
    BackgroundImportWorker,
)

DEV_BEARER = "diep-adms-import-dev-token-CHANGE-ME"
CORRELATION_ID = "11111111-1111-1111-1111-111111111111"
IDEMPOTENCY_KEY = "scheduler-import-001"


class FakePublishGateway:
    concurrency_model = ESTABLISHED_CONCURRENCY_MODEL
    atomic = True

    def publish(self, payload: TopologyPublishPayload, *, actor: str) -> TopologyPublishResult:
        return TopologyPublishResult(
            version=61,
            version_row={"version": 61, "label": payload.label, "actor": actor},
            nodes_written=len(payload.nodes),
            edges_written=len(payload.edges),
        )


@dataclass
class Clock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant

    def advance(self, seconds: int) -> None:
        self.instant += timedelta(seconds=seconds)


def _payload() -> dict:
    return {
        "contract_version": "1.0",
        "source_system": "adms-supplier-a",
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "import_mode": "full_snapshot",
        "external_model": {
            "model_id": "scheduler-model-a",
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
    payload = _payload()
    payload["idempotency_key"] = key
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
        body=json.dumps(payload),
    )


def _worker() -> BackgroundImportWorker:
    coordinator = build_import_coordinator(
        build_runtime_dependencies(
            publish_gateway=FakePublishGateway(),
            idempotency_store=InMemoryIdempotencyStore(),
            persistence_repository=InMemoryImportPersistenceRepository(),
        )
    )
    return BackgroundImportWorker(coordinator=coordinator)


def _schedule(
    schedule_id: str = "schedule-001",
    *,
    starts_at: datetime | None = None,
    key: str = IDEMPOTENCY_KEY,
    interval_seconds: int = 60,
    window: ExecutionWindow | None = None,
    max_occurrences: int | None = None,
) -> ScheduledImport:
    return ScheduledImport(
        schedule_id=schedule_id,
        request=_request(key),
        recurrence=RecurringExecutionPolicy(
            interval_seconds=interval_seconds,
            starts_at=starts_at,
            max_occurrences=max_occurrences,
        ),
        options=RuntimeExecutionOptions(actor="scheduler"),
        execution_window=window or ExecutionWindow(),
        max_attempts=2,
    )


def test_manual_trigger_enqueues_existing_background_worker_job():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 9, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(_schedule())
        record = await scheduler.manual_trigger("schedule-001")
        result = await worker.run_once()
        scheduler.reconcile_worker_results()
        return record, result, scheduler.executions

    record, result, executions = asyncio.run(scenario())

    assert record.trigger_reason == TRIGGER_REASON_MANUAL
    assert record.job_id == "schedule-001:1"
    assert result is not None
    assert result.status == JOB_COMPLETED
    assert result.runtime_result is not None
    assert result.runtime_result.steps_completed == RUNTIME_PIPELINE
    assert executions == (record,)


def test_scheduler_tick_enqueues_due_recurring_schedule_once():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 10, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(_schedule(starts_at=clock.now()))
        first = await scheduler.tick()
        second = await scheduler.tick()
        return first, second

    first, second = asyncio.run(scenario())

    assert len(first) == 1
    assert first[0].trigger_reason == TRIGGER_REASON_SCHEDULED
    assert first[0].job_id == "schedule-001:1"
    assert second == ()


def test_scheduler_recurs_after_worker_result_is_reconciled():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 10, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(
            _schedule(
                starts_at=clock.now(),
                interval_seconds=30,
                max_occurrences=2,
            )
        )
        first = await scheduler.tick()
        await worker.run_once()
        scheduler.reconcile_worker_results()
        clock.advance(30)
        second = await scheduler.tick()
        await worker.run_once()
        scheduler.reconcile_worker_results()
        clock.advance(30)
        third = await scheduler.tick()
        return first, second, third

    first, second, third = asyncio.run(scenario())

    assert first[0].job_id == "schedule-001:1"
    assert second[0].job_id == "schedule-001:2"
    assert third == ()


def test_execution_window_blocks_due_schedule_outside_window():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 3, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(
            _schedule(
                starts_at=clock.now(),
                window=ExecutionWindow(start_hour_utc=9, end_hour_utc=17),
            )
        )
        return await scheduler.tick()

    assert asyncio.run(scenario()) == ()


def test_wrapping_execution_window_allows_overnight_schedule():
    window = ExecutionWindow(start_hour_utc=22, end_hour_utc=2)

    assert window.contains(datetime(2026, 7, 8, 23, 0, tzinfo=UTC))
    assert window.contains(datetime(2026, 7, 9, 1, 0, tzinfo=UTC))
    assert not window.contains(datetime(2026, 7, 9, 12, 0, tzinfo=UTC))


def test_scheduler_rejects_duplicate_active_manual_trigger():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 9, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(_schedule())
        await scheduler.manual_trigger("schedule-001")
        with pytest.raises(AdmsImportSchedulerError) as raised:
            await scheduler.manual_trigger("schedule-001")
        return raised.value.reason_code

    assert asyncio.run(scenario()) == "schedule_already_active"


def test_scheduler_lifecycle_starts_and_stops_without_running_imports_itself():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 9, 0, tzinfo=UTC))
        scheduler = ImportScheduler(
            worker=worker,
            config=SchedulerConfig(poll_interval_seconds=0),
            now=clock.now,
        )
        scheduler.add_schedule(
            _schedule(starts_at=clock.now(), max_occurrences=1, key="scheduler-import-002")
        )
        await scheduler.start()
        while not scheduler.executions:
            await asyncio.sleep(0)
        assert scheduler.status == SCHEDULER_RUNNING
        assert worker.results == ()
        await scheduler.shutdown()
        return scheduler.status, scheduler.executions

    status, executions = asyncio.run(scenario())

    assert status == SCHEDULER_STOPPED
    assert len(executions) == 1


def test_disabled_schedule_is_not_enqueued_by_tick():
    async def scenario():
        worker = _worker()
        clock = Clock(datetime(2026, 7, 8, 9, 0, tzinfo=UTC))
        scheduler = ImportScheduler(worker=worker, now=clock.now)
        scheduler.add_schedule(disable_schedule(_schedule(starts_at=clock.now())))
        return await scheduler.tick()

    assert asyncio.run(scenario()) == ()


def test_scheduler_validates_configuration_deterministically():
    with pytest.raises(AdmsImportSchedulerError) as interval:
        RecurringExecutionPolicy(interval_seconds=0)
    with pytest.raises(AdmsImportSchedulerError) as window:
        ExecutionWindow(start_hour_utc=24).contains(datetime(2026, 7, 8, tzinfo=UTC))

    assert interval.value.reason_code == "invalid_interval"
    assert window.value.reason_code == "invalid_execution_window"
