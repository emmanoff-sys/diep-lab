"""Query and chain-verify API (ENG-SPEC-005-04 §11.3, §11.4).

Auth: user JWT aud=reos + admin:audit permission (AUD-SEC-004).
Meta-audit: GET /events emits audit.log.queried; verify-chain emits audit.chain.verified.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from audit_service.api.v1.schemas.audit_event import (
    AuditEventListResponse,
    AuditEventResponse,
    ChainVerifyResponse,
)
from audit_service.core.exceptions import (
    AuditChainNotFoundError,
    AuditEventNotFoundError,
    AuditInvalidPartitionTypeError,
    AuditQueryDateRangeTooLargeError,
    AuditQueryInvalidDateRangeError,
    AuditQueryInvalidDatetimeError,
    TokenValidationError,
)
from audit_service.core.security import decode_user_token
from audit_service.dependencies import get_audit_service
from audit_service.domain.services import AuditService

router = APIRouter(tags=["audit"])
logger = structlog.get_logger(__name__)

_no_jwt = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Missing or malformed Authorization header",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise _no_jwt
    return auth[len("Bearer ") :]


async def _validate_user_with_audit_permission(request: Request) -> dict[str, object]:
    raw_token = _extract_bearer(request)
    try:
        payload = await decode_user_token(raw_token)
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    # Permission check: admin:audit required (AUD-FR-008 / AUD-SEC-004)
    permissions: list[str] = payload.get("permissions", [])  # type: ignore[assignment]
    if "admin:audit" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "AUDIT_READ_UNAUTHORIZED", "detail": "admin:audit required"},
        )
    return payload  # type: ignore[return-value]


def _get_correlation_id(request: Request) -> UUID:
    raw = request.headers.get("X-Correlation-ID")
    if raw:
        try:
            return UUID(raw)
        except ValueError:
            pass
    return uuid4()


@router.get("/audit/events", response_model=AuditEventListResponse)
async def query_audit_events(
    request: Request,
    svc: AuditService = Depends(get_audit_service),
    actor_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    service_name: str | None = Query(default=None),
    correlation_id_filter: UUID | None = Query(default=None, alias="correlation_id"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> AuditEventListResponse:
    payload = await _validate_user_with_audit_permission(request)
    correlation_id = _get_correlation_id(request)

    actor_id_uuid = UUID(str(payload.get("sub", "")))

    from datetime import datetime

    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None

    try:
        result = await svc.query_events(
            requesting_actor_id=actor_id_uuid,
            requesting_actor_type="user",
            correlation_id=correlation_id,
            actor_id=actor_id,
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            service_name=service_name,
            filter_correlation_id=correlation_id_filter,
            date_from=df,
            date_to=dt,
            page=page,
            page_size=page_size,
            sort=sort,
        )
    except AuditQueryInvalidDatetimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "AUDIT_QUERY_INVALID_DATETIME", "detail": str(exc)},
        ) from exc
    except AuditQueryInvalidDateRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "AUDIT_QUERY_INVALID_DATE_RANGE", "detail": str(exc)},
        ) from exc
    except AuditQueryDateRangeTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "AUDIT_QUERY_DATE_RANGE_TOO_LARGE", "detail": str(exc)},
        ) from exc

    return AuditEventListResponse(
        events=[AuditEventResponse.model_validate(e) for e in result["events"]],
        total_count=result["total_count"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


@router.get("/audit/events/{event_id}", response_model=AuditEventResponse)
async def get_audit_event(
    event_id: UUID,
    request: Request,
    svc: AuditService = Depends(get_audit_service),
) -> AuditEventResponse:
    await _validate_user_with_audit_permission(request)

    try:
        event = await svc.get_event(event_id)
    except AuditEventNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "AUDIT_EVENT_NOT_FOUND", "detail": f"Event {event_id} not found"},
        ) from None
    return AuditEventResponse.model_validate(event)


@router.get(
    "/audit/verify-chain/{partition_type}/{partition_key}", response_model=ChainVerifyResponse
)
async def verify_chain(
    partition_type: str,
    partition_key: str,
    request: Request,
    svc: AuditService = Depends(get_audit_service),
) -> ChainVerifyResponse:
    payload = await _validate_user_with_audit_permission(request)
    correlation_id = _get_correlation_id(request)
    actor_id_uuid = UUID(str(payload.get("sub", "")))

    try:
        result = await svc.verify_chain(
            partition_type=partition_type,
            partition_key=partition_key,
            requesting_actor_id=actor_id_uuid,
            requesting_actor_type="user",
            correlation_id=correlation_id,
        )
    except AuditInvalidPartitionTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "AUDIT_INVALID_PARTITION_TYPE", "detail": str(exc)},
        ) from exc
    except AuditChainNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "AUDIT_CHAIN_NOT_FOUND", "detail": str(exc)},
        ) from exc

    return ChainVerifyResponse(**result)
