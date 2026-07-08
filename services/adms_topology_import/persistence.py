"""Persistence abstractions for ADMS topology import runtime state.

WP-006-08 Objective 12 defines repository contracts and deterministic
transaction semantics for import sessions, staging state, execution history,
and checkpoints. It does not introduce database schemas, APIs, workers,
schedulers, or alternative topology persistence models.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from typing import Any, Protocol

from .parser import ParsedAdmsTopologyImport
from .publish import PublishedTopologyImport
from .staging import StagedTopologyImport
from .transport import TransportValidationResult

ERROR_CATEGORY_PERSISTENCE = "persistence"

SESSION_STATUS_RECEIVED = "received"
SESSION_STATUS_PARSED = "parsed"
SESSION_STATUS_MAPPED = "mapped"
SESSION_STATUS_VALIDATED = "validated"
SESSION_STATUS_STAGED = "staged"
SESSION_STATUS_READY_FOR_PUBLISH = "ready_for_publish"
SESSION_STATUS_PUBLISHED = "published"


@dataclass(frozen=True)
class PersistenceDiagnostic:
    category: str
    reason_code: str
    description: str
    offending_object: str | None = None
    location: str | None = None


class AdmsImportPersistenceError(ValueError):
    """Deterministic persistence-layer error."""

    def __init__(
        self,
        *,
        reason_code: str,
        description: str,
        offending_object: str | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(f"{ERROR_CATEGORY_PERSISTENCE}:{reason_code}: {description}")
        self.diagnostic = PersistenceDiagnostic(
            category=ERROR_CATEGORY_PERSISTENCE,
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
class ImportSessionRecord:
    session_id: str
    correlation_id: str
    idempotency_key: str
    payload_sha256: str
    actor: str
    status: str
    source_system: str | None = None
    external_model_id: str | None = None
    external_model_version: str | None = None
    published_version: int | None = None


@dataclass(frozen=True)
class StagingPersistenceRecord:
    session_id: str
    staging_id: str
    status: str
    external_model_id: str
    external_model_version: str
    node_count: int
    edge_count: int
    lifecycle: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionHistoryRecord:
    sequence: int
    session_id: str
    step: str
    status: str
    reason: str


@dataclass(frozen=True)
class CheckpointRecord:
    sequence: int
    session_id: str
    step: str
    data: Mapping[str, Any]


class ImportPersistenceRepository(Protocol):
    """Repository boundary for runtime import persistence."""

    def transaction(self) -> AbstractContextManager[None]:
        """Provide an atomic persistence transaction."""

    def create_import_session(
        self,
        transport: TransportValidationResult,
        *,
        actor: str,
    ) -> ImportSessionRecord:
        """Persist an import session."""

    def update_import_session(
        self,
        session_id: str,
        *,
        status: str,
        parsed: ParsedAdmsTopologyImport | None = None,
        published: PublishedTopologyImport | None = None,
    ) -> ImportSessionRecord:
        """Update persisted import session state."""

    def save_staging(
        self,
        session_id: str,
        staged: StagedTopologyImport,
    ) -> StagingPersistenceRecord:
        """Persist staging state for an import session."""

    def append_history(
        self,
        session_id: str,
        *,
        step: str,
        status: str,
        reason: str = "",
    ) -> ExecutionHistoryRecord:
        """Append an execution history entry."""

    def record_checkpoint(
        self,
        session_id: str,
        *,
        step: str,
        data: Mapping[str, Any],
    ) -> CheckpointRecord:
        """Persist a deterministic execution checkpoint."""


class InMemoryImportPersistenceRepository:
    """Deterministic repository implementation for tests and DI boundaries."""

    def __init__(self) -> None:
        self._sessions: dict[str, ImportSessionRecord] = {}
        self._staging: dict[str, StagingPersistenceRecord] = {}
        self._history: list[ExecutionHistoryRecord] = []
        self._checkpoints: list[CheckpointRecord] = []
        self._sequence = 0
        self._transaction_active = False

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._transaction_active:
            _raise(
                "nested_transaction_not_supported",
                "Import persistence repository does not support nested transactions",
                location="transaction",
            )
        snapshot = self._snapshot()
        self._transaction_active = True
        try:
            yield
        except Exception:
            self._restore(snapshot)
            raise
        finally:
            self._transaction_active = False

    def create_import_session(
        self,
        transport: TransportValidationResult,
        *,
        actor: str,
    ) -> ImportSessionRecord:
        session_id = derive_session_id(transport.idempotency_key, transport.payload_sha256)
        if session_id in self._sessions:
            _raise(
                "duplicate_import_session",
                "Import session already exists",
                offending_object=session_id,
                location="session_id",
            )
        record = ImportSessionRecord(
            session_id=session_id,
            correlation_id=transport.correlation_id,
            idempotency_key=transport.idempotency_key,
            payload_sha256=transport.payload_sha256,
            actor=actor,
            status=SESSION_STATUS_RECEIVED,
        )
        self._sessions[session_id] = record
        return record

    def update_import_session(
        self,
        session_id: str,
        *,
        status: str,
        parsed: ParsedAdmsTopologyImport | None = None,
        published: PublishedTopologyImport | None = None,
    ) -> ImportSessionRecord:
        record = self._require_session(session_id)
        updated = replace(
            record,
            status=status,
            source_system=parsed.source_system if parsed else record.source_system,
            external_model_id=(
                parsed.external_model.model_id if parsed else record.external_model_id
            ),
            external_model_version=(
                parsed.external_model.model_version if parsed else record.external_model_version
            ),
            published_version=(
                published.published_version if published else record.published_version
            ),
        )
        self._sessions[session_id] = updated
        return updated

    def save_staging(
        self,
        session_id: str,
        staged: StagedTopologyImport,
    ) -> StagingPersistenceRecord:
        self._require_session(session_id)
        record = StagingPersistenceRecord(
            session_id=session_id,
            staging_id=staged.staging_id,
            status=staged.status,
            external_model_id=staged.topology.external_model_id,
            external_model_version=staged.topology.external_model_version,
            node_count=len(staged.topology.nodes),
            edge_count=len(staged.topology.edges),
            lifecycle=tuple(event.to_status for event in staged.lifecycle),
        )
        self._staging[session_id] = record
        return record

    def append_history(
        self,
        session_id: str,
        *,
        step: str,
        status: str,
        reason: str = "",
    ) -> ExecutionHistoryRecord:
        self._require_session(session_id)
        record = ExecutionHistoryRecord(
            sequence=self._next_sequence(),
            session_id=session_id,
            step=step,
            status=status,
            reason=reason,
        )
        self._history.append(record)
        return record

    def record_checkpoint(
        self,
        session_id: str,
        *,
        step: str,
        data: Mapping[str, Any],
    ) -> CheckpointRecord:
        self._require_session(session_id)
        record = CheckpointRecord(
            sequence=self._next_sequence(),
            session_id=session_id,
            step=step,
            data=copy.deepcopy(dict(data)),
        )
        self._checkpoints.append(record)
        return record

    def get_import_session(self, session_id: str) -> ImportSessionRecord | None:
        return self._sessions.get(session_id)

    def get_staging(self, session_id: str) -> StagingPersistenceRecord | None:
        return self._staging.get(session_id)

    def history_for_session(self, session_id: str) -> tuple[ExecutionHistoryRecord, ...]:
        return tuple(record for record in self._history if record.session_id == session_id)

    def checkpoints_for_session(self, session_id: str) -> tuple[CheckpointRecord, ...]:
        return tuple(record for record in self._checkpoints if record.session_id == session_id)

    def _require_session(self, session_id: str) -> ImportSessionRecord:
        record = self._sessions.get(session_id)
        if record is None:
            _raise(
                "unknown_import_session",
                "Import session does not exist",
                offending_object=session_id,
                location="session_id",
            )
        return record

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _snapshot(self) -> dict[str, Any]:
        return {
            "sessions": copy.deepcopy(self._sessions),
            "staging": copy.deepcopy(self._staging),
            "history": copy.deepcopy(self._history),
            "checkpoints": copy.deepcopy(self._checkpoints),
            "sequence": self._sequence,
        }

    def _restore(self, snapshot: Mapping[str, Any]) -> None:
        self._sessions = snapshot["sessions"]
        self._staging = snapshot["staging"]
        self._history = snapshot["history"]
        self._checkpoints = snapshot["checkpoints"]
        self._sequence = snapshot["sequence"]


def derive_session_id(idempotency_key: str, payload_sha256: str) -> str:
    """Derive a deterministic import session id."""

    material = f"{idempotency_key}|{payload_sha256}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"import-{digest}"


def _raise(
    reason_code: str,
    description: str,
    *,
    offending_object: str | None = None,
    location: str | None = None,
) -> None:
    raise AdmsImportPersistenceError(
        reason_code=reason_code,
        description=description,
        offending_object=offending_object,
        location=location,
    )
