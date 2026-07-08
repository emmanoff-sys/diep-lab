"""Failure recovery for ADMS topology import runtime.

WP-006-08 Objective 18 adds deterministic retry policy, checkpoint recovery,
partial rollback coordination, and recovery diagnostics. Recovery coordinates
existing persistence evidence and does not add APIs, production integration
testing, final validation, Release Engineering changes, governance updates, or
runtime architecture redesign.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parser import ParserDiagnostic
from .persistence import (
    SESSION_STATUS_MAPPED,
    SESSION_STATUS_PARSED,
    SESSION_STATUS_READY_FOR_PUBLISH,
    SESSION_STATUS_RECEIVED,
    SESSION_STATUS_RETRY_REQUESTED,
    SESSION_STATUS_STAGED,
    SESSION_STATUS_VALIDATED,
    TERMINAL_SESSION_STATUSES,
    CheckpointRecord,
    ExecutionHistoryRecord,
    ImportPersistenceRepository,
    ImportSessionRecord,
)
from .runtime import (
    STEP_MAP,
    STEP_PARSE,
    STEP_READY_FOR_PUBLISH,
    STEP_STAGE,
    STEP_TRANSPORT,
    STEP_VALIDATE,
)

ERROR_CATEGORY_RECOVERY = "recovery"

RECOVERY_STEP = "recovery"
RECOVERY_REASON_RETRY = "retry_requested_by_recovery"
RECOVERY_REASON_ROLLBACK = "rollback_to_checkpoint"

RECOVERABLE_REASON_CODES = frozenset(
    {
        "job_execution_failed",
        "temporary_failure",
        "publish_unavailable",
        "persistence_unavailable",
    }
)

CHECKPOINT_STEP_STATUSES = {
    STEP_TRANSPORT: SESSION_STATUS_RECEIVED,
    STEP_PARSE: SESSION_STATUS_PARSED,
    STEP_MAP: SESSION_STATUS_MAPPED,
    STEP_VALIDATE: SESSION_STATUS_VALIDATED,
    STEP_STAGE: SESSION_STATUS_STAGED,
    STEP_READY_FOR_PUBLISH: SESSION_STATUS_READY_FOR_PUBLISH,
}


@dataclass(frozen=True)
class RetryDecision:
    retry_allowed: bool
    next_attempt: int
    delay_seconds: float
    reason_code: str


@dataclass(frozen=True)
class RecoveryRetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.0
    max_delay_seconds: float = 0.0
    retryable_reason_codes: frozenset[str] = RECOVERABLE_REASON_CODES

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            _raise(
                "invalid_max_attempts",
                "Recovery retry max attempts must be positive",
                offending_object=str(self.max_attempts),
                location="retry_policy.max_attempts",
            )
        if self.base_delay_seconds < 0:
            _raise(
                "invalid_base_delay",
                "Recovery retry base delay must not be negative",
                offending_object=str(self.base_delay_seconds),
                location="retry_policy.base_delay_seconds",
            )
        if self.max_delay_seconds < 0:
            _raise(
                "invalid_max_delay",
                "Recovery retry max delay must not be negative",
                offending_object=str(self.max_delay_seconds),
                location="retry_policy.max_delay_seconds",
            )

    def decision_for(self, *, attempt: int, reason_code: str) -> RetryDecision:
        """Return a deterministic retry decision."""

        if attempt < 1:
            _raise(
                "invalid_retry_attempt",
                "Recovery retry attempt must be positive",
                offending_object=str(attempt),
                location="attempt",
            )
        retry_allowed = attempt < self.max_attempts and reason_code in self.retryable_reason_codes
        return RetryDecision(
            retry_allowed=retry_allowed,
            next_attempt=attempt + 1 if retry_allowed else attempt,
            delay_seconds=self._delay_for_attempt(attempt) if retry_allowed else 0.0,
            reason_code=reason_code,
        )

    def _delay_for_attempt(self, attempt: int) -> float:
        delay = self.base_delay_seconds * (2 ** (attempt - 1))
        if self.max_delay_seconds:
            return min(delay, self.max_delay_seconds)
        return delay


@dataclass(frozen=True)
class RecoveryDiagnostics:
    session_id: str
    session_status: str
    latest_checkpoint_step: str | None
    latest_checkpoint_sequence: int | None
    history_count: int
    checkpoint_count: int
    restorable: bool


@dataclass(frozen=True)
class CheckpointRecoveryResult:
    session: ImportSessionRecord
    checkpoint: CheckpointRecord
    restored_status: str
    history: ExecutionHistoryRecord
    recovery_checkpoint: CheckpointRecord


@dataclass(frozen=True)
class RecoveryRetryResult:
    session: ImportSessionRecord
    decision: RetryDecision
    history: ExecutionHistoryRecord | None = None
    checkpoint: CheckpointRecord | None = None


class AdmsImportRecoveryError(ValueError):
    """Deterministic failure-recovery error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_RECOVERY}:{reason_code}: {description}")
        self.diagnostic = ParserDiagnostic(
            category=ERROR_CATEGORY_RECOVERY,
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


class FailureRecoveryCoordinator:
    """Coordinate deterministic recovery using existing persistence records."""

    def __init__(
        self,
        *,
        repository: ImportPersistenceRepository,
        retry_policy: RecoveryRetryPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._retry_policy = retry_policy or RecoveryRetryPolicy()

    def diagnostics(self, session_id: str) -> RecoveryDiagnostics:
        """Return recovery diagnostics for a persisted import session."""

        session = self._require_session(session_id)
        checkpoints = self._repository.checkpoints_for_session(session_id)
        latest = checkpoints[-1] if checkpoints else None
        return RecoveryDiagnostics(
            session_id=session_id,
            session_status=session.status,
            latest_checkpoint_step=latest.step if latest else None,
            latest_checkpoint_sequence=latest.sequence if latest else None,
            history_count=len(self._repository.history_for_session(session_id)),
            checkpoint_count=len(checkpoints),
            restorable=(
                latest is not None
                and latest.step in CHECKPOINT_STEP_STATUSES
                and session.status not in TERMINAL_SESSION_STATUSES
            ),
        )

    def latest_checkpoint(self, session_id: str) -> CheckpointRecord:
        """Return the latest checkpoint for a persisted import session."""

        self._require_session(session_id)
        checkpoints = self._repository.checkpoints_for_session(session_id)
        if not checkpoints:
            _raise(
                "checkpoint_not_found",
                "Import session has no recovery checkpoint",
                offending_object=session_id,
                location="session_id",
            )
        return checkpoints[-1]

    def request_retry(
        self,
        session_id: str,
        *,
        attempt: int,
        reason_code: str,
    ) -> RecoveryRetryResult:
        """Record a retry request when the deterministic policy allows it."""

        session = self._require_session(session_id)
        decision = self._retry_policy.decision_for(attempt=attempt, reason_code=reason_code)
        if not decision.retry_allowed:
            return RecoveryRetryResult(session=session, decision=decision)

        with self._repository.transaction():
            updated = self._repository.update_import_session(
                session_id,
                status=SESSION_STATUS_RETRY_REQUESTED,
            )
            history = self._repository.append_history(
                session_id,
                step=RECOVERY_STEP,
                status=SESSION_STATUS_RETRY_REQUESTED,
                reason=RECOVERY_REASON_RETRY,
            )
            checkpoint = self._repository.record_checkpoint(
                session_id,
                step=RECOVERY_STEP,
                data={
                    "attempt": attempt,
                    "next_attempt": decision.next_attempt,
                    "reason_code": reason_code,
                    "delay_seconds": decision.delay_seconds,
                },
            )
        return RecoveryRetryResult(
            session=updated,
            decision=decision,
            history=history,
            checkpoint=checkpoint,
        )

    def rollback_to_latest_checkpoint(self, session_id: str) -> CheckpointRecoveryResult:
        """Coordinate partial rollback to the latest restorable checkpoint."""

        session = self._require_session(session_id)
        if session.status in TERMINAL_SESSION_STATUSES:
            _raise(
                "terminal_session_not_recoverable",
                "Terminal import sessions cannot be rolled back by failure recovery",
                offending_object=session_id,
                location="session_id",
            )
        checkpoint = self.latest_checkpoint(session_id)
        restored_status = CHECKPOINT_STEP_STATUSES.get(checkpoint.step)
        if restored_status is None:
            _raise(
                "checkpoint_not_restorable",
                "Latest checkpoint is not a restorable runtime checkpoint",
                offending_object=checkpoint.step,
                location="checkpoint.step",
            )

        with self._repository.transaction():
            updated = self._repository.update_import_session(
                session_id,
                status=restored_status,
            )
            history = self._repository.append_history(
                session_id,
                step=RECOVERY_STEP,
                status=restored_status,
                reason=f"{RECOVERY_REASON_ROLLBACK}:{checkpoint.step}",
            )
            recovery_checkpoint = self._repository.record_checkpoint(
                session_id,
                step=RECOVERY_STEP,
                data={
                    "rollback_checkpoint_sequence": checkpoint.sequence,
                    "rollback_step": checkpoint.step,
                    "restored_status": restored_status,
                },
            )
        return CheckpointRecoveryResult(
            session=updated,
            checkpoint=checkpoint,
            restored_status=restored_status,
            history=history,
            recovery_checkpoint=recovery_checkpoint,
        )

    def _require_session(self, session_id: str) -> ImportSessionRecord:
        session = self._repository.get_import_session(session_id)
        if session is None:
            _raise(
                "unknown_import_session",
                "Import session does not exist",
                offending_object=session_id,
                location="session_id",
            )
        return session


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportRecoveryError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
