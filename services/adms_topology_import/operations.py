"""Operational management for ADMS topology import runtime.

WP-006-08 Objective 17 adds import administration, operational metrics,
runtime diagnostics, execution reporting, operator controls, and recovery
visibility/control hooks. This module composes the existing persistence,
worker, and scheduler layers without adding production integration testing,
final validation, Release Engineering changes, governance updates, or runtime
architecture redesign.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from .parser import ParserDiagnostic
from .persistence import (
    TERMINAL_SESSION_STATUSES,
    ImportPersistenceRepository,
    ImportSessionRecord,
)
from .scheduler import ImportScheduler
from .worker import BackgroundImportWorker

ERROR_CATEGORY_OPERATIONS = "operations"

ACTION_CANCEL_JOB = "cancel_job"
ACTION_DISABLE_SCHEDULE = "disable_schedule"
ACTION_ENABLE_SCHEDULE = "enable_schedule"
ACTION_RECONCILE_SCHEDULER = "reconcile_scheduler"
ACTION_TRIGGER_SCHEDULE = "trigger_schedule"


@dataclass(frozen=True)
class OperationalMetricsSnapshot:
    session_count: int
    staging_count: int
    terminal_session_count: int
    non_terminal_session_count: int
    history_count: int
    checkpoint_count: int
    worker_result_count: int
    scheduler_execution_count: int
    sessions_by_status: dict[str, int]
    worker_results_by_status: dict[str, int]


@dataclass(frozen=True)
class RuntimeDiagnostics:
    repository_session_count: int
    worker_status: str | None
    worker_result_count: int
    scheduler_status: str | None
    scheduler_execution_count: int
    checked_at: str


@dataclass(frozen=True)
class ImportExecutionReport:
    session: ImportSessionRecord
    staging: Any | None
    history: tuple[Any, ...]
    checkpoints: tuple[Any, ...]


@dataclass(frozen=True)
class OperatorActionResult:
    action: str
    target: str
    status: str
    detail: str


class AdmsImportOperationsError(ValueError):
    """Deterministic operational-management error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_OPERATIONS}:{reason_code}: {description}")
        self.diagnostic = ParserDiagnostic(
            category=ERROR_CATEGORY_OPERATIONS,
            reason_code=reason_code,
            description=description,
            offending_object=offending_object,
            location=location,
        )

    @property
    def category(self) -> str:
        return self.diagnostic.category

    @property
    def reason_code(self) -> str:
        return self.diagnostic.reason_code

    @property
    def description(self) -> str:
        return self.diagnostic.description

    @property
    def offending_object(self) -> str | None:
        return self.diagnostic.offending_object

    @property
    def location(self) -> str | None:
        return self.diagnostic.location


class ImportOperationsManager:
    """Operational management facade over existing runtime components."""

    def __init__(
        self,
        *,
        repository: ImportPersistenceRepository,
        worker: BackgroundImportWorker | None = None,
        scheduler: ImportScheduler | None = None,
    ) -> None:
        self._repository = repository
        self._worker = worker
        self._scheduler = scheduler

    def metrics_snapshot(self) -> OperationalMetricsSnapshot:
        """Return deterministic operational counters for the import runtime."""

        sessions = self._repository.list_import_sessions()
        sessions_by_status = Counter(session.status for session in sessions)
        worker_results = self._worker.results if self._worker is not None else ()
        worker_results_by_status = Counter(result.status for result in worker_results)
        terminal = sum(1 for session in sessions if session.status in TERMINAL_SESSION_STATUSES)
        return OperationalMetricsSnapshot(
            session_count=len(sessions),
            staging_count=len(self._repository.list_staging_records()),
            terminal_session_count=terminal,
            non_terminal_session_count=len(sessions) - terminal,
            history_count=len(self._repository.list_execution_history()),
            checkpoint_count=len(self._repository.list_checkpoints()),
            worker_result_count=len(worker_results),
            scheduler_execution_count=(
                len(self._scheduler.executions) if self._scheduler is not None else 0
            ),
            sessions_by_status=dict(sorted(sessions_by_status.items())),
            worker_results_by_status=dict(sorted(worker_results_by_status.items())),
        )

    def diagnostics(self) -> RuntimeDiagnostics:
        """Return operational diagnostics without mutating runtime state."""

        return RuntimeDiagnostics(
            repository_session_count=len(self._repository.list_import_sessions()),
            worker_status=self._worker.status if self._worker is not None else None,
            worker_result_count=len(self._worker.results) if self._worker is not None else 0,
            scheduler_status=self._scheduler.status if self._scheduler is not None else None,
            scheduler_execution_count=(
                len(self._scheduler.executions) if self._scheduler is not None else 0
            ),
            checked_at=datetime.now(UTC).isoformat(),
        )

    def execution_report(self, session_id: str) -> ImportExecutionReport:
        """Return session execution evidence for operator review."""

        session = self._repository.get_import_session(session_id)
        if session is None:
            _raise(
                "unknown_import_session",
                "Import session does not exist",
                offending_object=session_id,
                location="session_id",
            )
        return ImportExecutionReport(
            session=session,
            staging=self._repository.get_staging(session_id),
            history=self._repository.history_for_session(session_id),
            checkpoints=self._repository.checkpoints_for_session(session_id),
        )

    def cancel_background_job(self, job_id: str) -> OperatorActionResult:
        """Request cancellation of a queued background job."""

        worker = self._require_worker()
        worker.cancel_job(job_id)
        return OperatorActionResult(
            action=ACTION_CANCEL_JOB,
            target=job_id,
            status="accepted",
            detail="background_job_cancel_requested",
        )

    async def trigger_schedule(self, schedule_id: str) -> OperatorActionResult:
        """Manually trigger a registered scheduled import."""

        scheduler = self._require_scheduler()
        record = await scheduler.manual_trigger(schedule_id, reason="operator_manual_trigger")
        return OperatorActionResult(
            action=ACTION_TRIGGER_SCHEDULE,
            target=record.job_id,
            status="accepted",
            detail="scheduled_import_triggered",
        )

    def reconcile_scheduler(self) -> OperatorActionResult:
        """Release scheduler visibility locks for completed worker jobs."""

        scheduler = self._require_scheduler()
        scheduler.reconcile_worker_results()
        return OperatorActionResult(
            action=ACTION_RECONCILE_SCHEDULER,
            target="scheduler",
            status="completed",
            detail="scheduler_worker_results_reconciled",
        )

    def disable_schedule(self, schedule_id: str) -> OperatorActionResult:
        """Disable a registered schedule through the scheduler replacement hook."""

        scheduler = self._require_scheduler()
        schedule = scheduler.get_schedule(schedule_id)
        scheduler.replace_schedule(replace(schedule, enabled=False))
        return OperatorActionResult(
            action=ACTION_DISABLE_SCHEDULE,
            target=schedule_id,
            status="completed",
            detail="schedule_disabled",
        )

    def enable_schedule(self, schedule_id: str) -> OperatorActionResult:
        """Enable a registered schedule through the scheduler replacement hook."""

        scheduler = self._require_scheduler()
        schedule = scheduler.get_schedule(schedule_id)
        scheduler.replace_schedule(replace(schedule, enabled=True))
        return OperatorActionResult(
            action=ACTION_ENABLE_SCHEDULE,
            target=schedule_id,
            status="completed",
            detail="schedule_enabled",
        )

    def _require_worker(self) -> BackgroundImportWorker:
        if self._worker is None:
            _raise(
                "worker_unavailable",
                "Background worker is required for this operator action",
                location="worker",
            )
        return self._worker

    def _require_scheduler(self) -> ImportScheduler:
        if self._scheduler is None:
            _raise(
                "scheduler_unavailable",
                "Import scheduler is required for this operator action",
                location="scheduler",
            )
        return self._scheduler


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportOperationsError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
