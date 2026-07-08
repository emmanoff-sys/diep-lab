"""Import scheduler for ADMS topology imports.

WP-006-08 Objective 15 adds scheduled import execution, manual trigger
scheduling, recurring execution policies, execution windows, scheduler
lifecycle management, scheduler configuration, and concurrency protection for
scheduled jobs. The scheduler delegates execution to the Objective 14
background worker and does not duplicate worker processing, persistence,
security, operational management, or recovery responsibilities.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from .runtime import RuntimeExecutionOptions
from .transport import TransportRequest
from .worker import BackgroundImportJob, BackgroundImportWorker

ERROR_CATEGORY_SCHEDULER = "scheduler"

SCHEDULER_STOPPED = "stopped"
SCHEDULER_RUNNING = "running"
SCHEDULER_STOPPING = "stopping"

TRIGGER_REASON_MANUAL = "manual"
TRIGGER_REASON_SCHEDULED = "scheduled"


@dataclass(frozen=True)
class SchedulerDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsImportSchedulerError(ValueError):
    """Deterministic import scheduler error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_SCHEDULER}:{reason_code}: {description}")
        self.diagnostic = SchedulerDiagnostic(
            category=ERROR_CATEGORY_SCHEDULER,
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


@dataclass(frozen=True)
class ExecutionWindow:
    """UTC hour window in which a schedule may enqueue import work."""

    start_hour_utc: int = 0
    end_hour_utc: int = 0

    def contains(self, instant: datetime) -> bool:
        """Return whether ``instant`` falls inside this UTC execution window."""

        _validate_hour(self.start_hour_utc, location="execution_window.start_hour_utc")
        _validate_hour(self.end_hour_utc, location="execution_window.end_hour_utc")
        hour = _as_utc(instant).hour
        if self.start_hour_utc == self.end_hour_utc:
            return True
        if self.start_hour_utc < self.end_hour_utc:
            return self.start_hour_utc <= hour < self.end_hour_utc
        return hour >= self.start_hour_utc or hour < self.end_hour_utc


@dataclass(frozen=True)
class RecurringExecutionPolicy:
    """Deterministic recurring execution policy for scheduled imports."""

    interval_seconds: int
    starts_at: datetime | None = None
    max_occurrences: int | None = None

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            _raise(
                "invalid_interval",
                "Recurring execution interval must be positive",
                offending_object=str(self.interval_seconds),
                location="recurrence.interval_seconds",
            )
        if self.max_occurrences is not None and self.max_occurrences <= 0:
            _raise(
                "invalid_max_occurrences",
                "Recurring execution max occurrences must be positive when provided",
                offending_object=str(self.max_occurrences),
                location="recurrence.max_occurrences",
            )

    def due_at(self, last_enqueued_at: datetime | None, *, now: datetime | None = None) -> datetime:
        """Return the next deterministic due time."""

        if last_enqueued_at is None:
            if self.starts_at is not None:
                return _as_utc(self.starts_at)
            return _as_utc(now) if now is not None else _utc_now()
        return _as_utc(last_enqueued_at) + timedelta(seconds=self.interval_seconds)

    def is_due(
        self,
        *,
        now: datetime,
        last_enqueued_at: datetime | None,
        occurrences: int,
    ) -> bool:
        """Return whether a schedule is due at ``now``."""

        if self.max_occurrences is not None and occurrences >= self.max_occurrences:
            return False
        return _as_utc(now) >= self.due_at(last_enqueued_at, now=now)


@dataclass(frozen=True)
class ScheduledImport:
    schedule_id: str
    request: TransportRequest
    recurrence: RecurringExecutionPolicy
    options: RuntimeExecutionOptions = RuntimeExecutionOptions()
    execution_window: ExecutionWindow = ExecutionWindow()
    enabled: bool = True
    max_attempts: int = 1


@dataclass(frozen=True)
class ScheduledExecutionRecord:
    schedule_id: str
    job_id: str
    due_at: datetime
    enqueued_at: datetime
    trigger_reason: str


@dataclass(frozen=True)
class SchedulerConfig:
    poll_interval_seconds: float = 1.0
    max_due_per_tick: int = 10

    def __post_init__(self) -> None:
        if self.poll_interval_seconds < 0:
            _raise(
                "invalid_poll_interval",
                "Scheduler poll interval must not be negative",
                offending_object=str(self.poll_interval_seconds),
                location="config.poll_interval_seconds",
            )
        if self.max_due_per_tick <= 0:
            _raise(
                "invalid_max_due_per_tick",
                "Scheduler max due per tick must be positive",
                offending_object=str(self.max_due_per_tick),
                location="config.max_due_per_tick",
            )


NowFn = Callable[[], datetime]
SleepFn = Callable[[float], Awaitable[None]]


class ImportScheduler:
    """Schedules ADMS import jobs for execution by a background worker."""

    def __init__(
        self,
        *,
        worker: BackgroundImportWorker,
        config: SchedulerConfig | None = None,
        now: NowFn | None = None,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._worker = worker
        self._config = config or SchedulerConfig()
        self._now = now or _utc_now
        self._sleep = sleep
        self._schedules: dict[str, ScheduledImport] = {}
        self._last_enqueued_at: dict[str, datetime] = {}
        self._occurrences: dict[str, int] = {}
        self._active_schedule_jobs: dict[str, str] = {}
        self._job_schedules: dict[str, str] = {}
        self._executions: list[ScheduledExecutionRecord] = []
        self._task: asyncio.Task[None] | None = None
        self._status = SCHEDULER_STOPPED

    @property
    def status(self) -> str:
        return self._status

    @property
    def executions(self) -> tuple[ScheduledExecutionRecord, ...]:
        return tuple(self._executions)

    def add_schedule(self, schedule: ScheduledImport) -> None:
        """Register a scheduled import definition."""

        _validate_schedule(schedule)
        if schedule.schedule_id in self._schedules:
            _raise(
                "duplicate_schedule",
                "Scheduled import id already exists",
                offending_object=schedule.schedule_id,
                location="schedule_id",
            )
        self._schedules[schedule.schedule_id] = schedule
        self._occurrences.setdefault(schedule.schedule_id, 0)

    def replace_schedule(self, schedule: ScheduledImport) -> None:
        """Replace an existing scheduled import definition."""

        _validate_schedule(schedule)
        if schedule.schedule_id not in self._schedules:
            _raise(
                "unknown_schedule",
                "Scheduled import id is not registered",
                offending_object=schedule.schedule_id,
                location="schedule_id",
            )
        if schedule.schedule_id in self._active_schedule_jobs:
            _raise(
                "schedule_already_active",
                "Scheduled import already has an active job",
                offending_object=schedule.schedule_id,
                location="schedule_id",
            )
        self._schedules[schedule.schedule_id] = schedule

    def remove_schedule(self, schedule_id: str) -> None:
        """Remove a scheduled import definition."""

        self._require_schedule(schedule_id)
        if schedule_id in self._active_schedule_jobs:
            _raise(
                "schedule_already_active",
                "Scheduled import already has an active job",
                offending_object=schedule_id,
                location="schedule_id",
            )
        del self._schedules[schedule_id]
        self._last_enqueued_at.pop(schedule_id, None)
        self._occurrences.pop(schedule_id, None)

    def get_schedule(self, schedule_id: str) -> ScheduledImport:
        """Return a registered schedule."""

        return self._require_schedule(schedule_id)

    async def manual_trigger(
        self,
        schedule_id: str,
        *,
        reason: str = TRIGGER_REASON_MANUAL,
    ) -> ScheduledExecutionRecord:
        """Enqueue a registered schedule immediately."""

        schedule = self._require_schedule(schedule_id)
        now = _as_utc(self._now())
        return await self._enqueue(schedule, due_at=now, enqueued_at=now, reason=reason)

    async def tick(self) -> tuple[ScheduledExecutionRecord, ...]:
        """Enqueue due scheduled imports for the current scheduler instant."""

        self.reconcile_worker_results()
        now = _as_utc(self._now())
        records: list[ScheduledExecutionRecord] = []
        for schedule in self._schedules.values():
            if len(records) >= self._config.max_due_per_tick:
                break
            if not self._is_due(schedule, now):
                continue
            record = await self._enqueue(
                schedule,
                due_at=schedule.recurrence.due_at(
                    self._last_enqueued_at.get(schedule.schedule_id),
                    now=now,
                ),
                enqueued_at=now,
                reason=TRIGGER_REASON_SCHEDULED,
            )
            records.append(record)
        return tuple(records)

    async def start(self) -> None:
        """Start the scheduler lifecycle loop."""

        if self._task is not None and not self._task.done():
            _raise(
                "scheduler_already_running",
                "Import scheduler is already running",
                location="scheduler.status",
            )
        self._status = SCHEDULER_RUNNING
        self._task = asyncio.create_task(self._run_loop())

    async def shutdown(self) -> None:
        """Gracefully stop the scheduler loop."""

        if self._task is None:
            self._status = SCHEDULER_STOPPED
            return
        self._status = SCHEDULER_STOPPING
        await self._task
        self._task = None
        self._status = SCHEDULER_STOPPED

    def reconcile_worker_results(self) -> None:
        """Release schedule concurrency locks for completed worker results."""

        for result in self._worker.results:
            schedule_id = self._job_schedules.get(result.job_id)
            if schedule_id is None:
                continue
            if self._active_schedule_jobs.get(schedule_id) == result.job_id:
                del self._active_schedule_jobs[schedule_id]

    async def _run_loop(self) -> None:
        while self._status == SCHEDULER_RUNNING:
            await self.tick()
            await self._sleep(self._config.poll_interval_seconds)

    def _is_due(self, schedule: ScheduledImport, now: datetime) -> bool:
        if not schedule.enabled:
            return False
        if schedule.schedule_id in self._active_schedule_jobs:
            return False
        if not schedule.execution_window.contains(now):
            return False
        return schedule.recurrence.is_due(
            now=now,
            last_enqueued_at=self._last_enqueued_at.get(schedule.schedule_id),
            occurrences=self._occurrences.get(schedule.schedule_id, 0),
        )

    async def _enqueue(
        self,
        schedule: ScheduledImport,
        *,
        due_at: datetime,
        enqueued_at: datetime,
        reason: str,
    ) -> ScheduledExecutionRecord:
        if schedule.schedule_id in self._active_schedule_jobs:
            _raise(
                "schedule_already_active",
                "Scheduled import already has an active job",
                offending_object=schedule.schedule_id,
                location="schedule_id",
            )
        occurrence = self._occurrences.get(schedule.schedule_id, 0) + 1
        job_id = f"{schedule.schedule_id}:{occurrence}"
        job = BackgroundImportJob(
            job_id=job_id,
            request=schedule.request,
            options=schedule.options,
            max_attempts=schedule.max_attempts,
        )
        await self._worker.enqueue(job)
        record = ScheduledExecutionRecord(
            schedule_id=schedule.schedule_id,
            job_id=job_id,
            due_at=_as_utc(due_at),
            enqueued_at=_as_utc(enqueued_at),
            trigger_reason=reason,
        )
        self._active_schedule_jobs[schedule.schedule_id] = job_id
        self._job_schedules[job_id] = schedule.schedule_id
        self._last_enqueued_at[schedule.schedule_id] = record.enqueued_at
        self._occurrences[schedule.schedule_id] = occurrence
        self._executions.append(record)
        return record

    def _require_schedule(self, schedule_id: str) -> ScheduledImport:
        if not schedule_id.strip():
            _raise(
                "invalid_schedule_id",
                "Scheduled import id must be non-empty",
                offending_object=schedule_id,
                location="schedule_id",
            )
        schedule = self._schedules.get(schedule_id)
        if schedule is None:
            _raise(
                "unknown_schedule",
                "Scheduled import id is not registered",
                offending_object=schedule_id,
                location="schedule_id",
            )
        return schedule


def disable_schedule(schedule: ScheduledImport) -> ScheduledImport:
    """Return a disabled copy of a scheduled import definition."""

    return replace(schedule, enabled=False)


def _validate_schedule(schedule: ScheduledImport) -> None:
    if not schedule.schedule_id.strip():
        _raise(
            "invalid_schedule_id",
            "Scheduled import id must be non-empty",
            offending_object=schedule.schedule_id,
            location="schedule_id",
        )
    if schedule.max_attempts <= 0:
        _raise(
            "invalid_max_attempts",
            "Scheduled import max attempts must be positive",
            offending_object=str(schedule.max_attempts),
            location="max_attempts",
        )
    schedule.execution_window.contains(_utc_now())


def _validate_hour(hour: int, *, location: str) -> None:
    if hour < 0 or hour > 23:
        _raise(
            "invalid_execution_window",
            "Execution window hour must be between 0 and 23 inclusive",
            offending_object=str(hour),
            location=location,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportSchedulerError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
