"""MFA endpoints (SRS SEC-004 / SEC-005 — WP-005-02).

Endpoint map:
  TOTP setup (authenticated user or mfa-setup-required token):
    POST /api/v1/auth/mfa/totp/setup          — generate secret + provisioning URI
    POST /api/v1/auth/mfa/totp/setup/complete — confirm enrolment with first code

  TOTP verification (login flow, mfa-pending token):
    POST /api/v1/auth/mfa/totp/verify         — verify code → full token pair

  SMS (stubbed until WP-005-05):
    POST /api/v1/auth/mfa/sms/send            — trigger OTP send (stub)
    POST /api/v1/auth/mfa/sms/verify          — verify OTP → full token pair

  FIDO2 / WebAuthn:
    POST /api/v1/auth/mfa/fido2/register          — begin credential registration (get options)
    POST /api/v1/auth/mfa/fido2/register/complete — complete registration (verify response)
    POST /api/v1/auth/mfa/fido2/assert            — begin authentication (get options)
    POST /api/v1/auth/mfa/fido2/assert/complete   — complete authentication → full token pair

  Admin:
    POST /api/v1/admin/mfa/unlock/{user_id}   — admin MFA unlock (SEC-005)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import redis.asyncio as aioredis
from identity_service.config import settings
from identity_service.core import kafka
from identity_service.core import mfa as mfa_core
from identity_service.core import mfa_lockout
from identity_service.core.jwt import jwt_manager
from identity_service.core.rbac import RequirePermission
from identity_service.core.security import get_current_user
from identity_service.db.session import get_db
from identity_service.models.user import User
from identity_service.models.webauthn_credential import WebAuthnCredential
from identity_service.schemas.mfa import (
    Fido2AssertCompleteRequest,
    Fido2AssertResponse,
    Fido2RegisterCompleteRequest,
    Fido2RegisterResponse,
    MfaTokenResponse,
    MfaUnlockResponse,
    SmsSendRequest,
    SmsSendResponse,
    SmsVerifyRequest,
    TotpSetupCompleteRequest,
    TotpSetupResponse,
    TotpVerifyRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mfa"])


def _mfa_audit(
    event_type: str,
    action: str,
    actor_id: UUID,
    outcome: str = "success",
    outcome_reason: str | None = None,
) -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "actor_type": "user",
        "actor_id": str(actor_id),
        "action": action,
        "resource_type": "mfa",
        "resource_id": None,
        "outcome": outcome,
        "outcome_reason": outcome_reason,
        "correlation_id": str(uuid4()),
        "service_name": settings.SERVICE_NAME,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "schema_version": 1,
    }


def _get_redis(request: Request) -> aioredis.Redis:
    return cast(aioredis.Redis, request.app.state.redis)


def _rt_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _rt_ttl(client_type: str) -> int:
    return (
        settings.JWT_REFRESH_TOKEN_TTL_MOBILE
        if client_type == "mobile"
        else settings.JWT_REFRESH_TOKEN_TTL_WEB
    )


def _user_permissions(user: User) -> list[str]:
    perms: set[str] = set()
    for role in user.roles:
        for p in role.permissions:
            perms.add(p.slug)
    return sorted(perms)


async def _issue_full_token_pair(
    redis: aioredis.Redis,
    user: User,
    client_type: str = "web",
) -> MfaTokenResponse:
    """Issue access + refresh tokens after successful MFA completion."""
    roles = [r.name for r in user.roles]
    permissions = _user_permissions(user)
    access_token = jwt_manager.create_access_token(
        subject=user.id, roles=roles, permissions=permissions
    )
    rt = jwt_manager.create_refresh_token()
    rt_hash = _rt_hash(rt)
    rt_payload = json.dumps({"user_id": str(user.id), "client_type": client_type})
    await redis.set(f"rt:{rt_hash}", rt_payload, ex=_rt_ttl(client_type))
    return MfaTokenResponse(
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TOKEN_TTL,
        refresh_token=rt,
    )


def _decode_mfa_pending(token: str, expected_type: str = "mfa-pending") -> dict[str, object]:
    try:
        return jwt_manager.decode_mfa_pending_token(token, expected_type=expected_type)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired MFA token: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# TOTP setup
# ---------------------------------------------------------------------------


@router.post(
    "/auth/mfa/totp/setup",
    response_model=TotpSetupResponse,
    summary="Begin TOTP enrolment — returns secret and provisioning URI (SEC-004)",
)
async def totp_setup(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpSetupResponse:
    """Generate a TOTP secret and provisioning URI.

    Requires an authenticated user (Bearer access token or mfa-setup-required intermediate
    token handled at the get_current_user level).  The secret is NOT yet persisted until
    /totp/setup/complete confirms the first code.
    """
    redis = _get_redis(request)
    secret = mfa_core.generate_totp_secret()
    uri = mfa_core.get_totp_provisioning_uri(secret, user.email)
    # Store pending secret in Redis (not DB yet — confirmed only after first code validates)
    await redis.set(f"mfa:totp_pending:{user.id}", secret, ex=settings.MFA_SETUP_TOKEN_TTL)
    logger.info("mfa.totp.setup_initiated", extra={"user_id": str(user.id)})
    return TotpSetupResponse(secret=secret, provisioning_uri=uri)


@router.post(
    "/auth/mfa/totp/setup/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Complete TOTP enrolment — verify first code (SEC-004)",
)
async def totp_setup_complete(
    body: TotpSetupCompleteRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    redis = _get_redis(request)
    raw = await redis.getdel(f"mfa:totp_pending:{user.id}")
    if not raw:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No pending TOTP setup — call /auth/mfa/totp/setup first",
        )
    secret = raw.decode() if isinstance(raw, bytes) else raw

    if not mfa_core.verify_totp(secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")

    encrypted = mfa_core.encrypt_totp_secret(secret)
    user.mfa_secret = encrypted
    user.mfa_enabled = True
    if "totp" not in user.mfa_methods:
        user.mfa_methods = list(user.mfa_methods) + ["totp"]
    db.add(user)
    await db.commit()
    logger.info("mfa.totp.enrolled", extra={"user_id": str(user.id)})


# ---------------------------------------------------------------------------
# TOTP verification (login flow)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/mfa/totp/verify",
    response_model=MfaTokenResponse,
    summary="Verify TOTP code during login — returns full token pair (SEC-004)",
)
async def totp_verify(
    body: TotpVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MfaTokenResponse:
    redis = _get_redis(request)
    claims = _decode_mfa_pending(body.mfa_pending_token, "mfa-pending")
    user_id = UUID(str(claims["sub"]))

    if await mfa_lockout.is_mfa_locked(redis, str(user_id)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="MFA locked — too many failed attempts",
        )

    user = await db.get(User, user_id)
    if not user or not user.is_active or not user.mfa_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="MFA not configured")

    plaintext_secret = mfa_core.decrypt_totp_secret(user.mfa_secret)
    if not mfa_core.verify_totp(plaintext_secret, body.code):
        locked = await mfa_lockout.record_mfa_failure(
            redis,
            str(user_id),
            settings.MFA_LOCKOUT_MAX_ATTEMPTS,
            settings.MFA_LOCKOUT_WINDOW_SECONDS,
            settings.MFA_LOCKED_TTL_SECONDS,
        )
        logger.warning("mfa.totp.verify_failed", extra={"user_id": str(user_id), "locked": locked})
        _etype = "auth.mfa.locked" if locked else "auth.mfa.failed"
        asyncio.create_task(
            kafka.publish_iam_audit_event(
                _mfa_audit(
                    event_type=_etype,
                    action="mfa.failed" if not locked else "mfa.locked",
                    actor_id=user_id,
                    outcome="failure",
                    outcome_reason="totp_locked" if locked else "invalid_totp",
                )
            )
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")

    await mfa_lockout.clear_mfa_failures(redis, str(user_id))
    logger.info("mfa.totp.verified", extra={"user_id": str(user_id)})
    asyncio.create_task(
        kafka.publish_iam_audit_event(
            _mfa_audit(
                event_type="auth.mfa.verified",
                action="mfa.verified",
                actor_id=user_id,
            )
        )
    )
    return await _issue_full_token_pair(redis, user)


# ---------------------------------------------------------------------------
# SMS (stub)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/mfa/sms/send",
    response_model=SmsSendResponse,
    summary="Send SMS OTP during login (stubbed — WP-005-05)",
)
async def sms_send(
    body: SmsSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SmsSendResponse:
    redis = _get_redis(request)
    claims = _decode_mfa_pending(body.mfa_pending_token, "mfa-pending")
    user_id = str(claims["sub"])
    await mfa_core.generate_and_store_sms_otp(redis, user_id)
    return SmsSendResponse()


@router.post(
    "/auth/mfa/sms/verify",
    response_model=MfaTokenResponse,
    summary="Verify SMS OTP during login — returns full token pair (SEC-004)",
)
async def sms_verify(
    body: SmsVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MfaTokenResponse:
    redis = _get_redis(request)
    claims = _decode_mfa_pending(body.mfa_pending_token, "mfa-pending")
    user_id_str = str(claims["sub"])
    user_id = UUID(user_id_str)

    if await mfa_lockout.is_mfa_locked(redis, user_id_str):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="MFA locked — too many failed attempts",
        )

    ok = await mfa_core.verify_sms_otp(redis, user_id_str, body.code)
    if not ok:
        locked = await mfa_lockout.record_mfa_failure(
            redis,
            user_id_str,
            settings.MFA_LOCKOUT_MAX_ATTEMPTS,
            settings.MFA_LOCKOUT_WINDOW_SECONDS,
            settings.MFA_LOCKED_TTL_SECONDS,
        )
        logger.warning("mfa.sms.verify_failed", extra={"user_id": user_id_str, "locked": locked})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid SMS OTP")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")

    await mfa_lockout.clear_mfa_failures(redis, user_id_str)
    logger.info("mfa.sms.verified", extra={"user_id": user_id_str})
    return await _issue_full_token_pair(redis, user)


# ---------------------------------------------------------------------------
# FIDO2 registration (authenticated user enrolling a new credential)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/mfa/fido2/register",
    response_model=Fido2RegisterResponse,
    summary="Begin FIDO2 credential registration — returns WebAuthn options (SEC-004)",
)
async def fido2_register_begin(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Fido2RegisterResponse:
    redis = _get_redis(request)
    existing = await db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )
    cred_list = [{"credential_id": c.credential_id} for c in existing.all()]
    options = await mfa_core.begin_fido2_registration(redis, str(user.id), user.email, cred_list)
    return Fido2RegisterResponse(options=options)


@router.post(
    "/auth/mfa/fido2/register/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Complete FIDO2 credential registration — verify and store (SEC-004)",
)
async def fido2_register_complete(
    body: Fido2RegisterCompleteRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    redis = _get_redis(request)
    try:
        result = await mfa_core.complete_fido2_registration(redis, str(user.id), body.credential)
    except (ValueError, Exception) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=result["credential_id"],
        public_key=result["public_key"],
        sign_count=result["sign_count"],
    )
    db.add(cred)

    if not user.mfa_enabled:
        user.mfa_enabled = True
    if "fido2" not in user.mfa_methods:
        user.mfa_methods = list(user.mfa_methods) + ["fido2"]

    await db.commit()
    logger.info(
        "mfa.fido2.enrolled",
        extra={"user_id": str(user.id), "credential_id": result["credential_id"]},
    )


# ---------------------------------------------------------------------------
# FIDO2 assertion (login flow)
# ---------------------------------------------------------------------------


@router.post(
    "/auth/mfa/fido2/assert",
    response_model=Fido2AssertResponse,
    summary="Begin FIDO2 authentication — returns WebAuthn options (SEC-004)",
)
async def fido2_assert_begin(
    body: SmsSendRequest,  # reuse — only needs mfa_pending_token
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Fido2AssertResponse:
    redis = _get_redis(request)
    claims = _decode_mfa_pending(body.mfa_pending_token, "mfa-pending")
    user_id = UUID(str(claims["sub"]))

    existing = await db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    )
    cred_list = [{"credential_id": c.credential_id} for c in existing.all()]

    options = await mfa_core.begin_fido2_assertion(redis, str(user_id), cred_list)
    return Fido2AssertResponse(options=options, mfa_pending_token=body.mfa_pending_token)


@router.post(
    "/auth/mfa/fido2/assert/complete",
    response_model=MfaTokenResponse,
    summary="Complete FIDO2 authentication — verify assertion → full token pair (SEC-004)",
)
async def fido2_assert_complete(
    body: Fido2AssertCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MfaTokenResponse:
    redis = _get_redis(request)
    claims = _decode_mfa_pending(body.mfa_pending_token, "mfa-pending")
    user_id_str = str(claims["sub"])
    user_id = UUID(user_id_str)

    if await mfa_lockout.is_mfa_locked(redis, user_id_str):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="MFA locked — too many failed attempts",
        )

    existing_qs = await db.scalars(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    )
    stored_creds = existing_qs.all()
    cred_list = [
        {
            "credential_id": c.credential_id,
            "public_key": c.public_key,
            "sign_count": c.sign_count,
        }
        for c in stored_creds
    ]

    try:
        ok = await mfa_core.complete_fido2_assertion(redis, user_id_str, body.credential, cred_list)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not ok:
        locked = await mfa_lockout.record_mfa_failure(
            redis,
            user_id_str,
            settings.MFA_LOCKOUT_MAX_ATTEMPTS,
            settings.MFA_LOCKOUT_WINDOW_SECONDS,
            settings.MFA_LOCKED_TTL_SECONDS,
        )
        logger.warning("mfa.fido2.assert_failed", extra={"user_id": user_id_str, "locked": locked})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="FIDO2 assertion failed")

    # Persist updated sign_count for the matched credential
    for stored, live in zip(stored_creds, cred_list, strict=False):
        if stored.credential_id == live["credential_id"]:
            stored.sign_count = int(cast(str | int, live["sign_count"]))
            db.add(stored)
    await db.commit()

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")

    await mfa_lockout.clear_mfa_failures(redis, user_id_str)
    logger.info("mfa.fido2.asserted", extra={"user_id": user_id_str})
    return await _issue_full_token_pair(redis, user)


# ---------------------------------------------------------------------------
# Admin MFA unlock (SEC-005 — admin can unlock manually)
# ---------------------------------------------------------------------------


@router.post(
    "/admin/mfa/unlock/{user_id}",
    response_model=MfaUnlockResponse,
    summary="Admin: manually unlock a user's MFA lockout (SEC-005)",
)
async def admin_mfa_unlock(
    user_id: str,
    request: Request,
    current_user: User = Depends(RequirePermission("admin:users")),
) -> MfaUnlockResponse:
    redis = _get_redis(request)
    await mfa_lockout.admin_unlock_mfa(redis, user_id)
    logger.info("mfa.admin_unlock", extra={"user_id": user_id})
    asyncio.create_task(
        kafka.publish_iam_audit_event(
            _mfa_audit(
                event_type="auth.mfa.admin_unlocked",
                action="mfa.admin_unlock",
                actor_id=current_user.id,
                outcome="success",
            )
        )
    )
    return MfaUnlockResponse(user_id=user_id)
