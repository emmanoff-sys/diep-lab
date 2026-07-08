"""FastAPI router for the ADMS topology import runtime.

WP-006-08 Objective 13 exposes production REST endpoints over the existing
runtime orchestration and persistence layers. It does not add workers,
scheduling, new security mechanisms, operational management, or recovery logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Request, status

from .mapping import AdmsTopologyMappingError
from .observability import health_snapshot
from .parser import AdmsContractParserError
from .persistence import (
    SESSION_STATUS_CANCELLED,
    SESSION_STATUS_RETRY_REQUESTED,
    TERMINAL_SESSION_STATUSES,
    AdmsImportPersistenceError,
    CheckpointRecord,
    ExecutionHistoryRecord,
    ImportSessionRecord,
    InMemoryImportPersistenceRepository,
    derive_session_id,
)
from .publish import AdmsTopologyPublishError
from .runtime import (
    AdmsImportCoordinator,
    AdmsImportRuntimeError,
    RuntimeExecutionOptions,
    RuntimeExecutionResult,
)
from .staging import AdmsTopologyStagingError
from .transport import TransportRequest, TransportValidationError
from .validation import AdmsTopologyValidationError


class SubmitImportRequest(BaseModel):
    payload: dict[str, Any] = Field(..., description="ADMS topology import contract payload")
    actor: str = "adms-runtime"
    label: str | None = None
    description: str | None = None
    site_name: str | None = None
    staging_id: str | None = None


class RetryImportRequest(BaseModel):
    reason: str = "operator_retry"


class ImportSubmissionResponse(BaseModel):
    session_id: str
    status: str
    correlation_id: str
    idempotency_key: str
    staging_id: str | None = None
    published_version: int | None = None
    steps_completed: list[str]


class ImportStatusResponse(BaseModel):
    session_id: str
    status: str
    correlation_id: str
    idempotency_key: str
    actor: str
    source_system: str | None = None
    external_model_id: str | None = None
    external_model_version: str | None = None
    staging_id: str | None = None
    published_version: int | None = None


class HistoryItemResponse(BaseModel):
    sequence: int
    step: str
    status: str
    reason: str


class CheckpointItemResponse(BaseModel):
    sequence: int
    step: str
    data: dict[str, Any]


class ImportHistoryResponse(BaseModel):
    session_id: str
    history: list[HistoryItemResponse]
    checkpoints: list[CheckpointItemResponse]


class RuntimeHealthResponse(BaseModel):
    service: str
    ready: bool
    metrics_enabled: bool
    detail: str | None = None


@dataclass(frozen=True)
class RuntimeApiState:
    coordinator: AdmsImportCoordinator
    repository: InMemoryImportPersistenceRepository
    metrics_enabled: bool = True


def create_runtime_router(
    *,
    coordinator: AdmsImportCoordinator,
    repository: InMemoryImportPersistenceRepository,
    prefix: str = "/adms/topology-imports",
    metrics_enabled: bool = True,
) -> APIRouter:
    """Create the ADMS import runtime router with injected dependencies."""

    state = RuntimeApiState(
        coordinator=coordinator,
        repository=repository,
        metrics_enabled=metrics_enabled,
    )
    router = APIRouter(prefix=prefix, tags=["adms-topology-import"])

    @router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ImportSubmissionResponse)
    async def submit_import(
        body: SubmitImportRequest, request: Request
    ) -> ImportSubmissionResponse:
        transport = _transport_request(request, body.payload)
        options = RuntimeExecutionOptions(
            actor=body.actor,
            label=body.label,
            description=body.description,
            site_name=body.site_name,
            staging_id=body.staging_id,
        )
        try:
            result = state.coordinator.submit(transport, options=options)
        except Exception as exc:
            _raise_http(exc)
        return _submission_response(result)

    @router.get("/-/health", response_model=RuntimeHealthResponse)
    def runtime_health() -> RuntimeHealthResponse:
        snapshot = health_snapshot(
            metrics_enabled=state.metrics_enabled,
            ready=True,
            detail="runtime_api_ready",
        )
        return RuntimeHealthResponse(
            service=snapshot["service"],
            ready=snapshot["ready"],
            metrics_enabled=snapshot["metrics_enabled"],
            detail=snapshot["detail"],
        )

    @router.get("/{session_id}", response_model=ImportStatusResponse)
    def import_status(session_id: str) -> ImportStatusResponse:
        return _status_response(_require_session(state.repository, session_id), state.repository)

    @router.post("/{session_id}/cancel", response_model=ImportStatusResponse)
    def cancel_import(session_id: str) -> ImportStatusResponse:
        session = _require_session(state.repository, session_id)
        if session.status in TERMINAL_SESSION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "category": "runtime_api",
                    "reason_code": "import_already_terminal",
                    "description": "Import session is already terminal",
                    "offending_object": session_id,
                    "location": "session_id",
                },
            )
        with state.repository.transaction():
            session = state.repository.update_import_session(
                session_id,
                status=SESSION_STATUS_CANCELLED,
            )
            state.repository.append_history(
                session_id,
                step="cancel",
                status=SESSION_STATUS_CANCELLED,
                reason="operator_cancelled",
            )
            state.repository.record_checkpoint(
                session_id,
                step="cancel",
                data={"status": SESSION_STATUS_CANCELLED},
            )
        return _status_response(session, state.repository)

    @router.post("/{session_id}/retry", response_model=ImportStatusResponse)
    def retry_import(session_id: str, body: RetryImportRequest) -> ImportStatusResponse:
        session = _require_session(state.repository, session_id)
        if session.status in TERMINAL_SESSION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "category": "runtime_api",
                    "reason_code": "import_already_terminal",
                    "description": (
                        "Terminal import sessions cannot be retried by the synchronous API"
                    ),
                    "offending_object": session_id,
                    "location": "session_id",
                },
            )
        with state.repository.transaction():
            session = state.repository.update_import_session(
                session_id,
                status=SESSION_STATUS_RETRY_REQUESTED,
            )
            state.repository.append_history(
                session_id,
                step="retry",
                status=SESSION_STATUS_RETRY_REQUESTED,
                reason=body.reason,
            )
            state.repository.record_checkpoint(
                session_id,
                step="retry",
                data={"reason": body.reason},
            )
        return _status_response(session, state.repository)

    @router.get("/{session_id}/history", response_model=ImportHistoryResponse)
    def import_history(session_id: str) -> ImportHistoryResponse:
        _require_session(state.repository, session_id)
        return ImportHistoryResponse(
            session_id=session_id,
            history=[
                _history_item(record) for record in state.repository.history_for_session(session_id)
            ],
            checkpoints=[
                _checkpoint_item(record)
                for record in state.repository.checkpoints_for_session(session_id)
            ],
        )

    return router


def _transport_request(request: Request, payload: dict[str, Any]) -> TransportRequest:
    return TransportRequest(
        method=request.method,
        scheme=request.url.scheme,
        headers=dict(request.headers),
        body=json.dumps(payload),
        tls_version=request.headers.get("x-tls-version"),
        client_certificate_subject=request.headers.get("x-client-certificate-subject"),
    )


def _submission_response(result: RuntimeExecutionResult) -> ImportSubmissionResponse:
    return ImportSubmissionResponse(
        session_id=derive_session_id(
            result.transport.idempotency_key, result.transport.payload_sha256
        ),
        status=result.status,
        correlation_id=result.transport.correlation_id,
        idempotency_key=result.transport.idempotency_key,
        staging_id=result.staged.staging_id if result.staged else None,
        published_version=result.published.published_version if result.published else None,
        steps_completed=list(result.steps_completed),
    )


def _require_session(
    repository: InMemoryImportPersistenceRepository,
    session_id: str,
) -> ImportSessionRecord:
    session = repository.get_import_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "category": "runtime_api",
                "reason_code": "unknown_import_session",
                "description": "Import session does not exist",
                "offending_object": session_id,
                "location": "session_id",
            },
        )
    return session


def _status_response(
    session: ImportSessionRecord,
    repository: InMemoryImportPersistenceRepository,
) -> ImportStatusResponse:
    staging = repository.get_staging(session.session_id)
    return ImportStatusResponse(
        session_id=session.session_id,
        status=session.status,
        correlation_id=session.correlation_id,
        idempotency_key=session.idempotency_key,
        actor=session.actor,
        source_system=session.source_system,
        external_model_id=session.external_model_id,
        external_model_version=session.external_model_version,
        staging_id=staging.staging_id if staging else None,
        published_version=session.published_version,
    )


def _history_item(record: ExecutionHistoryRecord) -> HistoryItemResponse:
    return HistoryItemResponse(
        sequence=record.sequence,
        step=record.step,
        status=record.status,
        reason=record.reason,
    )


def _checkpoint_item(record: CheckpointRecord) -> CheckpointItemResponse:
    return CheckpointItemResponse(
        sequence=record.sequence,
        step=record.step,
        data=dict(record.data),
    )


def _raise_http(exc: Exception) -> None:
    diagnostic = getattr(exc, "diagnostic", None)
    if diagnostic is None:
        raise exc
    status_code = 422
    if isinstance(exc, TransportValidationError):
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if exc.category == "authentication"
            else status.HTTP_400_BAD_REQUEST
        )
    elif isinstance(
        exc,
        (
            AdmsImportPersistenceError,
            AdmsImportRuntimeError,
            AdmsTopologyPublishError,
            AdmsTopologyStagingError,
        ),
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(
        exc,
        (
            AdmsContractParserError,
            AdmsTopologyMappingError,
            AdmsTopologyValidationError,
        ),
    ):
        status_code = 422
    raise HTTPException(
        status_code=status_code,
        detail={
            "category": diagnostic.category,
            "reason_code": diagnostic.reason_code,
            "description": diagnostic.description,
            "offending_object": diagnostic.offending_object,
            "location": diagnostic.location,
        },
    )
