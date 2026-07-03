"""MFA request/response schemas (SRS SEC-004 / WP-005-02)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Intermediate token responses (login flow — SEC-004 MFA enforcement)
# ---------------------------------------------------------------------------


class MfaPendingResponse(BaseModel):
    """Returned from /auth/token when a privileged user has MFA enabled."""

    mfa_required: bool = True
    mfa_pending_token: str
    mfa_methods: list[str]  # enrolled methods the user can choose from


class MfaSetupRequiredResponse(BaseModel):
    """Returned from /auth/token when a privileged user has NOT yet enrolled MFA."""

    mfa_setup_required: bool = True
    mfa_setup_token: str  # short-lived token granting access to MFA setup endpoints only


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------


class TotpSetupResponse(BaseModel):
    """Response from POST /auth/mfa/totp/setup — secret + provisioning URI."""

    secret: str
    provisioning_uri: str


class TotpSetupCompleteRequest(BaseModel):
    """Confirm TOTP enrolment by verifying the first code after scanning the QR."""

    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class TotpVerifyRequest(BaseModel):
    """Verify TOTP during login flow (requires mfa_pending_token)."""

    mfa_pending_token: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------


class SmsSendRequest(BaseModel):
    """Trigger an SMS OTP send during login flow."""

    mfa_pending_token: str


class SmsSendResponse(BaseModel):
    sent: bool = True
    note: str = "SMS delivery is stubbed pending WP-005-05 Notification Service"


class SmsVerifyRequest(BaseModel):
    """Verify an SMS OTP during login flow."""

    mfa_pending_token: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


# ---------------------------------------------------------------------------
# FIDO2 / WebAuthn
# ---------------------------------------------------------------------------


class Fido2RegisterResponse(BaseModel):
    """WebAuthn registration options returned to the client."""

    options: dict[str, Any]


class Fido2RegisterCompleteRequest(BaseModel):
    """WebAuthn registration response from the authenticator."""

    credential: dict[str, Any]


class Fido2AssertResponse(BaseModel):
    """WebAuthn authentication options returned to the client."""

    options: dict[str, Any]
    mfa_pending_token: str


class Fido2AssertCompleteRequest(BaseModel):
    """WebAuthn assertion response from the authenticator during login."""

    mfa_pending_token: str
    credential: dict[str, Any]


# ---------------------------------------------------------------------------
# Admin unlock (SEC-005)
# ---------------------------------------------------------------------------


class MfaUnlockResponse(BaseModel):
    unlocked: bool = True
    user_id: str


# ---------------------------------------------------------------------------
# Generic MFA completion (returned after any successful MFA verification)
# ---------------------------------------------------------------------------


class MfaTokenResponse(BaseModel):
    """Full access + refresh tokens issued after successful MFA verification."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str | None = None
    scope: str = "openid"
