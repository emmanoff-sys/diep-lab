"""Internal write API — POST /api/v1/audit/events (ENG-SPEC-005-04 §11.2).

Auth: service JWT, aud=reos-internal only (AUD-SEC-003).
User JWTs are rejected with 403 (wrong audience → TokenValidationError).
"""

from __future__ import annotations

import structlog
from audit_service.api.v1.schemas.audit_event import AuditEventCreate, AuditEventResponse
from audit_service.core.exceptions import (
    AuditEventDuplicateError,
    TokenValidationError,
)
from audit_service.core.security import decode_service_token
from audit_service.dependencies import get_audit_service

from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter(tags=["internal"])
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


@router.post(
    "/audit/events",
    response_model=AuditEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def write_audit_event(
    body: AuditEventCreate,
    request: Request,
    svc: AuditService = Depends(get_audit_service),  # type: ignore[name-defined]
) -> AuditEventResponse:
    raw_token = _extract_bearer(request)
    try:
        await decode_service_token(raw_token)
    except TokenValidationError as exc:
        if "audience" in str(exc).lower() or "aud" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error_code": "AUDIT_WRITE_UNAUTHORIZED", "detail": str(exc)},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    event_dict = body.model_dump()
    try:
        event = await svc.write_event(event_dict, source="rest")
    except AuditEventDuplicateError as exc:
        # 409: return the existing event
        existing = await svc.get_event(exc.event_id)
        return AuditEventResponse.model_validate(existing)

    return AuditEventResponse.model_validate(event)


# Re-export for router registration
from audit_service.domain.services import AuditService  # noqa: E402
