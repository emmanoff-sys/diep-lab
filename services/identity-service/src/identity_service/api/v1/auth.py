"""OAuth2 Authorization Code + PKCE endpoints (SRS SEC-001/002/003).

Endpoints:
  POST /api/v1/auth/register   — create account, emit user.registered Kafka event
  POST /api/v1/auth/login      — verify credentials, issue single-use auth code
  POST /api/v1/auth/token      — exchange auth code + code_verifier for tokens
  POST /api/v1/auth/refresh    — rotate refresh token, issue new access token
  POST /api/v1/auth/revoke     — revoke refresh token

Redis key scheme:
  auth_code:{code}             — JSON {user_id, code_challenge, client_id, client_type}, TTL=600s
  rt:{sha256(token)}           — JSON {user_id, client_id, client_type}, TTL=RTT
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from identity_service.config import settings
from identity_service.core import kafka, lockout
from identity_service.core import mfa as mfa_core
from identity_service.core import pkce
from identity_service.core.jwt import jwt_manager
from identity_service.core.password import hash_password, verify_password
from identity_service.db.session import get_db
from identity_service.models.role import Role
from identity_service.models.user import User
from identity_service.schemas.auth import (
    AuthCodeResponse,
    GrantType,
    TokenResponse,
)
from identity_service.schemas.mfa import MfaPendingResponse, MfaSetupRequiredResponse
from identity_service.schemas.user import LoginRequest, UserRegisterRequest, UserResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _audit_event(
    event_type: str,
    action: str,
    actor_id: UUID,
    outcome: str,
    resource_type: str = "session",
    resource_id: str | None = None,
    correlation_id: UUID | None = None,
    outcome_reason: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build an iam.audit.events payload (ENG-SPEC-005-04 §10.2)."""
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "actor_type": "user",
        "actor_id": str(actor_id),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome,
        "outcome_reason": outcome_reason,
        "correlation_id": str(correlation_id or uuid4()),
        "service_name": settings.SERVICE_NAME,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "schema_version": 1,
        "metadata": metadata,
    }


def _get_redis(request: Request) -> aioredis.Redis:  # type: ignore[type-arg]
    return request.app.state.redis  # type: ignore[no-any-return]


def _rt_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _rt_ttl(client_type: str) -> int:
    if client_type == "mobile":
        return settings.JWT_REFRESH_TOKEN_TTL_MOBILE
    return settings.JWT_REFRESH_TOKEN_TTL_WEB


def _user_permissions(user: User) -> list[str]:
    perms: set[str] = set()
    for role in user.roles:
        for p in role.permissions:
            perms.add(p.slug)
    return sorted(perms)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    existing = await db.scalar(
        select(User).where(
            or_(User.email == body.email.lower(), User.username == body.username.lower())
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email or username already registered")

    password_hash = hash_password(body.password)
    user = User(
        email=body.email.lower(),
        username=body.username.lower(),
        password_hash=password_hash,
    )

    # Assign default 'customer' role
    customer_role = await db.scalar(select(Role).where(Role.name == "customer"))
    if customer_role:
        user.roles.append(customer_role)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    await kafka.publish_user_registered(user.id, user.email)
    logger.info("user.registered", user_id=str(user.id))

    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        is_email_verified=user.is_email_verified,
        roles=[r.name for r in user.roles],
    )


# ---------------------------------------------------------------------------
# Login → auth code (PKCE step 1)
# ---------------------------------------------------------------------------


@router.post("/login", response_model=AuthCodeResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthCodeResponse:
    redis = _get_redis(request)
    identifier = body.username_or_email.lower()

    if await lockout.is_blocked(redis, identifier):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked — too many failed attempts",
        )

    user = await db.scalar(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    # Constant-time failure path — always verify even if user not found (prevent timing attacks)
    password_ok = verify_password(body.password, user.password_hash) if user else False

    if not user or not password_ok or not user.is_active:
        blocked = await lockout.record_failure(
            redis,
            identifier,
            settings.LOCKOUT_MAX_FAILURES,
            settings.LOCKOUT_TTL_SECONDS,
        )
        logger.warning("auth.login_failed", identifier=identifier, locked=blocked)
        # Emit audit event — actor_id is a nil UUID when user not found
        _actor = user.id if user else UUID(int=0)
        _etype = "auth.login.locked" if blocked else "auth.login.failure"
        asyncio.create_task(
            kafka.publish_iam_audit_event(
                _audit_event(
                    event_type=_etype,
                    action="login",
                    actor_id=_actor,
                    outcome="failure",
                    outcome_reason="invalid_credentials" if not blocked else "account_locked",
                )
            )
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    await lockout.clear_failures(redis, identifier)
    asyncio.create_task(
        kafka.publish_iam_audit_event(
            _audit_event(
                event_type="auth.login.success",
                action="login",
                actor_id=user.id,
                outcome="success",
            )
        )
    )

    code = pkce.generate_auth_code()
    auth_code_payload = json.dumps(
        {
            "user_id": str(user.id),
            "code_challenge": body.code_challenge,
            "client_id": body.client_id,
            "client_type": body.client_type,
        }
    )
    await redis.set(
        f"auth_code:{code}",
        auth_code_payload,
        ex=settings.JWT_AUTH_CODE_TTL,
    )
    logger.info("auth.code_issued", user_id=str(user.id))
    return AuthCodeResponse(code=code)


# ---------------------------------------------------------------------------
# Token exchange (PKCE step 2)
# ---------------------------------------------------------------------------


@router.post("/token", response_model=TokenResponse | MfaPendingResponse | MfaSetupRequiredResponse)
async def token(
    request: Request,
    grant_type: str = Form(...),
    code: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    client_type: str = Form(default="web"),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    redis = _get_redis(request)

    if grant_type == GrantType.AUTHORIZATION_CODE:
        return await _exchange_auth_code(redis, db, code, code_verifier, client_id, client_type)
    if grant_type == GrantType.REFRESH_TOKEN:
        return await _refresh(redis, db, refresh_token, client_type)
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail={"error": "unsupported_grant_type"},
    )


async def _exchange_auth_code(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    db: AsyncSession,
    code: str | None,
    code_verifier: str | None,
    client_id: str | None,
    client_type: str,
) -> TokenResponse:
    if not code or not code_verifier:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_request",
                "error_description": "code and code_verifier required",
            },
        )

    raw = await redis.getdel(f"auth_code:{code}")  # atomic get+delete → single-use
    if not raw:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_grant",
                "error_description": "Authorization code invalid or expired",
            },
        )

    stored: dict[str, str] = json.loads(raw)

    if not pkce.verify_pkce(code_verifier, stored["code_challenge"]):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_grant", "error_description": "PKCE verification failed"},
        )
    if client_id and client_id != stored.get("client_id"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_client"},
        )

    user = await db.get(User, UUID(stored["user_id"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "access_denied"})

    resolved_client_type = stored.get("client_type", client_type)

    # SEC-004: enforce MFA for privileged roles before issuing full tokens
    role_names = [r.name for r in user.roles]
    if mfa_core.is_mfa_required_role(role_names):
        if user.mfa_enabled:
            mfa_token = jwt_manager.create_mfa_pending_token(
                user.id,
                token_type="mfa-pending",  # noqa: S106 — MFA state token type, not a credential
            )
            logger.info("auth.mfa_pending_issued", user_id=str(user.id))
            return MfaPendingResponse(
                mfa_pending_token=mfa_token,
                mfa_methods=list(user.mfa_methods),
            )
        else:
            setup_token = jwt_manager.create_mfa_pending_token(
                user.id,
                token_type="mfa-setup-required",  # noqa: S106 — MFA state token type, not a credential
            )
            logger.warning("auth.mfa_setup_required", user_id=str(user.id))
            return MfaSetupRequiredResponse(mfa_setup_token=setup_token)

    asyncio.create_task(
        kafka.publish_iam_audit_event(
            _audit_event(
                event_type="auth.token.exchanged",
                action="token.exchange",
                actor_id=user.id,
                outcome="success",
            )
        )
    )
    return await _issue_token_pair(redis, user, resolved_client_type)


async def _refresh(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    db: AsyncSession,
    refresh_token: str | None,
    client_type: str,
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_request", "error_description": "refresh_token required"},
        )

    token_hash = _rt_hash(refresh_token)
    raw = await redis.getdel(f"rt:{token_hash}")  # single-use rotation
    if not raw:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_grant",
                "error_description": "Refresh token invalid or expired",
            },
        )

    stored: dict[str, str] = json.loads(raw)
    user = await db.get(User, UUID(stored["user_id"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail={"error": "access_denied"})

    resolved_client_type = stored.get("client_type", client_type)

    asyncio.create_task(
        kafka.publish_iam_audit_event(
            _audit_event(
                event_type="auth.token.refreshed",
                action="token.refresh",
                actor_id=user.id,
                outcome="success",
            )
        )
    )
    return await _issue_token_pair(redis, user, resolved_client_type)


async def _issue_token_pair(
    redis: aioredis.Redis,  # type: ignore[type-arg]
    user: User,
    client_type: str,
) -> TokenResponse:
    roles = [r.name for r in user.roles]
    permissions = _user_permissions(user)

    access_token = jwt_manager.create_access_token(
        subject=user.id, roles=roles, permissions=permissions
    )
    rt = jwt_manager.create_refresh_token()
    rt_hash = _rt_hash(rt)
    rt_ttl = _rt_ttl(client_type)

    rt_payload = json.dumps(
        {
            "user_id": str(user.id),
            "client_type": client_type,
        }
    )
    await redis.set(f"rt:{rt_hash}", rt_payload, ex=rt_ttl)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TOKEN_TTL,
        refresh_token=rt,
    )


# ---------------------------------------------------------------------------
# Token revocation
# ---------------------------------------------------------------------------


@router.post("/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    request: Request,
    token: str = Form(...),
    token_type_hint: str = Form(default="refresh_token"),
) -> None:
    redis = _get_redis(request)
    token_hash = _rt_hash(token)
    raw = await redis.getdel(f"rt:{token_hash}")

    if raw:
        try:
            stored: dict[str, str] = json.loads(raw)
            actor_id = UUID(stored["user_id"])
            asyncio.create_task(
                kafka.publish_iam_audit_event(
                    _audit_event(
                        event_type="auth.token.revoked",
                        action="token.revoke",
                        actor_id=actor_id,
                        outcome="success",
                    )
                )
            )
        except Exception:  # noqa: S110 — best-effort audit; must not block revocation
            pass
