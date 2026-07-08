"""Background worker framework for ADMS topology imports.

WP-006-08 Objective 14 adds asynchronous execution, queue abstraction, worker
lifecycle management, retry scheduling primitives, graceful shutdown, and
cancellation handling around the existing runtime coordinator. It does not add
scheduled imports, production security, operational management, recovery
mechanisms, APIs, or alternate runtime orchestration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Protocol

from .runtime import (
    AdmsImportCoordinator,
    RuntimeExecutionOptions,
    RuntimeExecutionResult,
)
from .transport import TransportRequest

ERROR_CATEGORY_WORKER = "worker"

WORKER_STOPPED = "stopped"
WORKER_RUNNING = "running"
WORKER_STOPPING = "stopping"

JOB_COMPLETED = "completed"
JOB_CANCELLED = "cancelled"
JOB_FAILED = "failed"
JOB_RETRY_SCHEDULED = "retry_scheduled"

_STOP = object()


@dataclass(frozen=True)
class WorkerDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsImportWorkerError(ValueError):
    """Deterministic background worker error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_WORKER}:{reason_code}: {description}")
        self.diagnostic = WorkerDiagnostic(
            category=ERROR_CATEGORY_WORKER,
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
class BackgroundImportJob:
    job_id: str
    request: TransportRequest
    options: RuntimeExecutionOptions = RuntimeExecutionOptions()
    attempt: int = 1
    max_attempts: int = 1


@dataclass(frozen=True)
class BackgroundImportResult:
    job_id: str
    status: str
    attempt: int
    runtime_result: RuntimeExecutionResult | None = None
    diagnostic: WorkerDiagnostic | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    base_delay_seconds: float = 0.0
    max_delay_seconds: float = 0.0

    def delay_for_attempt(self, attempt: int) -> float:
        """Return deterministic retry delay for the next attempt."""

        if attempt < 1:
            _raise(
                "invalid_retry_attempt",
                "Retry attempt must be positive",
                offending_object=str(attempt),
                location="attempt",
            )
        delay = self.base_delay_seconds * (2 ** (attempt - 1))
        if self.max_delay_seconds:
            return min(delay, self.max_delay_seconds)
        return delay

    def attempts_for(self, job: BackgroundImportJob) -> int:
        """Resolve the attempt limit for a job."""

        return max(job.max_attempts, self.max_attempts)


class ImportJobQueue(Protocol):
    """Queue boundary consumed by the background worker."""

    async def put(self, job: BackgroundImportJob | object) -> None:
        """Add a job or stop marker to the queue."""

    async def get(self) -> BackgroundImportJob | object:
        """Return the next queued job or stop marker."""

    def task_done(self) -> None:
        """Mark the current queue item complete."""


class InMemoryImportJobQueue:
    """In-memory async queue for tests and dependency injection."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[BackgroundImportJob | object] = asyncio.Queue()

    async def put(self, job: BackgroundImportJob | object) -> None:
        await self._queue.put(job)

    async def get(self) -> BackgroundImportJob | object:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def qsize(self) -> int:
        return self._queue.qsize()


SleepFn = Callable[[float], Awaitable[None]]


class BackgroundImportWorker:
    """Asynchronous worker that executes queued ADMS import jobs."""

    def __init__(
        self,
        *,
        coordinator: AdmsImportCoordinator,
        queue: ImportJobQueue | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._coordinator = coordinator
        self._queue = queue or InMemoryImportJobQueue()
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._status = WORKER_STOPPED
        self._cancelled_jobs: set[str] = set()
        self._results: list[BackgroundImportResult] = []

    @property
    def status(self) -> str:
        return self._status

    @property
    def results(self) -> tuple[BackgroundImportResult, ...]:
        return tuple(self._results)

    async def enqueue(self, job: BackgroundImportJob) -> None:
        """Queue a background import job."""

        if not job.job_id.strip():
            _raise(
                "invalid_job_id",
                "Background import job id must be non-empty",
                offending_object=job.job_id,
                location="job_id",
            )
        await self._queue.put(job)

    def cancel_job(self, job_id: str) -> None:
        """Mark a queued job as cancelled before execution."""

        if not job_id.strip():
            _raise(
                "invalid_job_id",
                "Background import job id must be non-empty",
                offending_object=job_id,
                location="job_id",
            )
        self._cancelled_jobs.add(job_id)

    async def start(self) -> None:
        """Start the background worker loop."""

        if self._task is not None and not self._task.done():
            _raise(
                "worker_already_running",
                "Background import worker is already running",
                location="worker.status",
            )
        self._status = WORKER_RUNNING
        self._task = asyncio.create_task(self._run_loop())

    async def shutdown(self) -> None:
        """Gracefully stop the background worker loop."""

        if self._task is None:
            self._status = WORKER_STOPPED
            return
        self._status = WORKER_STOPPING
        await self._queue.put(_STOP)
        await self._task
        self._task = None
        self._status = WORKER_STOPPED

    async def run_once(self) -> BackgroundImportResult | None:
        """Process a single queued item and return its result."""

        item = await self._queue.get()
        try:
            if item is _STOP:
                return None
            return await self._handle_job(_require_job(item))
        finally:
            self._queue.task_done()

    async def _run_loop(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is _STOP:
                    return
                await self._handle_job(_require_job(item))
            finally:
                self._queue.task_done()

    async def _handle_job(self, job: BackgroundImportJob) -> BackgroundImportResult:
        if job.job_id in self._cancelled_jobs:
            result = BackgroundImportResult(
                job_id=job.job_id,
                status=JOB_CANCELLED,
                attempt=job.attempt,
                diagnostic=WorkerDiagnostic(
                    category=ERROR_CATEGORY_WORKER,
                    reason_code="job_cancelled",
                    description="Background import job was cancelled before execution",
                    offending_object=job.job_id,
                    location="job_id",
                ),
            )
            self._results.append(result)
            return result

        try:
            runtime_result = self._coordinator.submit(job.request, options=job.options)
        except Exception as exc:  # noqa: BLE001 - worker boundary captures job failure
            return await self._handle_failure(job, exc)

        result = BackgroundImportResult(
            job_id=job.job_id,
            status=JOB_COMPLETED,
            attempt=job.attempt,
            runtime_result=runtime_result,
        )
        self._results.append(result)
        return result

    async def _handle_failure(
        self,
        job: BackgroundImportJob,
        exc: Exception,
    ) -> BackgroundImportResult:
        diagnostic = _diagnostic_from_exception(job, exc)
        max_attempts = self._retry_policy.attempts_for(job)
        if job.attempt < max_attempts:
            delay = self._retry_policy.delay_for_attempt(job.attempt)
            if delay:
                await self._sleep(delay)
            await self._queue.put(replace(job, attempt=job.attempt + 1, max_attempts=max_attempts))
            result = BackgroundImportResult(
                job_id=job.job_id,
                status=JOB_RETRY_SCHEDULED,
                attempt=job.attempt,
                diagnostic=diagnostic,
            )
            self._results.append(result)
            return result

        result = BackgroundImportResult(
            job_id=job.job_id,
            status=JOB_FAILED,
            attempt=job.attempt,
            diagnostic=diagnostic,
        )
        self._results.append(result)
        return result


def _require_job(item: BackgroundImportJob | object) -> BackgroundImportJob:
    if not isinstance(item, BackgroundImportJob):
        _raise(
            "invalid_queue_item",
            "Import worker queue item must be a BackgroundImportJob",
            offending_object=type(item).__name__,
            location="queue",
        )
    return item


def _diagnostic_from_exception(job: BackgroundImportJob, exc: Exception) -> WorkerDiagnostic:
    source = getattr(exc, "diagnostic", None)
    if source is not None:
        reason_code = source.reason_code
        description = source.description
    else:
        reason_code = "job_execution_failed"
        description = str(exc)
    return WorkerDiagnostic(
        category=ERROR_CATEGORY_WORKER,
        reason_code=reason_code,
        description=description,
        offending_object=job.job_id,
        location="job",
    )


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportWorkerError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
