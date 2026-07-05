"""MFA logic: TOTP, SMS (stubbed), FIDO2/WebAuthn (SRS SEC-004).

Design decisions (flagged per engineering governance):
  - TOTP secret encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
    In production MFA_SECRET_ENCRYPTION_KEY is injected from Vault KV via env var
    (WP-003-13 Vault agent pattern).  Full Vault Transit integration is a WP-005-09
    shared-library enhancement — flagged, not silently deferred.
  - SMS delivery is stubbed with a logged no-op pending WP-005-05 Notification Service.
    The stub method signature IS the interface contract for WP-005-05 to fulfil.
  - FIDO2 challenges are stored in Redis (TTL = MFA_WEBAUTHN_CHALLENGE_TTL).
  - py_webauthn (webauthn package) is used for WebAuthn operations.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
from typing import Any, cast

import pyotp
import redis.asyncio as aioredis
from cryptography.fernet import Fernet, InvalidToken
from identity_service.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fernet key helper
# ---------------------------------------------------------------------------

_fernet: Fernet | None = None


def _get_fernet() -> Fernet | None:
    """Return the Fernet instance if an encryption key is configured."""
    global _fernet  # noqa: PLW0603
    if _fernet is not None:
        return _fernet
    key = settings.MFA_SECRET_ENCRYPTION_KEY
    if not key:
        return None
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def _encrypt_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for DB storage.  Returns base64url ciphertext."""
    fernet = _get_fernet()
    if fernet is None:
        return plaintext  # test/dev mode: store plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def _decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored TOTP secret.  Raises ValueError on tampering."""
    fernet = _get_fernet()
    if fernet is None:
        return ciphertext
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("TOTP secret decryption failed — possible tampering") from exc


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------


def generate_totp_secret() -> str:
    """Generate a 32-character base32 TOTP secret (pyotp standard length)."""
    return cast(str, pyotp.random_base32())


def get_totp_provisioning_uri(secret: str, email: str) -> str:
    """Return an otpauth:// URI suitable for QR-code display."""
    totp = pyotp.TOTP(secret)
    return cast(str, totp.provisioning_uri(name=email, issuer_name=settings.MFA_TOTP_ISSUER))


def verify_totp(secret: str, code: str, window: int | None = None) -> bool:
    """Validate a 6-digit TOTP code with ±window time-step tolerance."""
    if window is None:
        window = settings.MFA_TOTP_WINDOW
    totp = pyotp.TOTP(secret)
    return cast(bool, totp.verify(code, valid_window=window))


def encrypt_totp_secret(plaintext: str) -> str:
    return _encrypt_secret(plaintext)


def decrypt_totp_secret(ciphertext: str) -> str:
    return _decrypt_secret(ciphertext)


# ---------------------------------------------------------------------------
# SMS OTP (stub — interface contract for WP-005-05)
# ---------------------------------------------------------------------------
#
# SEC-004 mandates SMS as a supported MFA channel.  The Notification Service
# (WP-005-05) is not yet built.  This stub:
#   1. Logs the send as a no-op (does NOT deliver a real SMS).
#   2. Stores a generated OTP in Redis with MFA_SMS_OTP_TTL so that
#      verify_sms_otp() can still function in integration tests.
# This stub IS the interface contract.  WP-005-05 MUST fulfil this exact
# signature: async def send_sms_otp(phone: str, otp: str) -> None.


async def generate_and_store_sms_otp(
    redis: aioredis.Redis,
    user_id: str,
) -> str:
    """Generate a 6-digit OTP, store in Redis, stub-send via SMS.  Returns OTP (for tests)."""
    otp = str(secrets.randbelow(900000) + 100000)  # 100000–999999
    await redis.set(f"mfa:sms_otp:{user_id}", otp, ex=settings.MFA_SMS_OTP_TTL)
    # STUB: replace with real Notification Service call when WP-005-05 lands.
    logger.warning(
        "mfa.sms_otp.stub",
        extra={
            "user_id": user_id,
            "note": "SMS delivery is stubbed — WP-005-05 Notification Service not yet built",
        },
    )
    return otp


async def verify_sms_otp(
    redis: aioredis.Redis,
    user_id: str,
    provided_code: str,
) -> bool:
    """Verify a submitted SMS OTP code.  Single-use via GETDEL."""
    stored = await redis.getdel(f"mfa:sms_otp:{user_id}")
    if not stored:
        return False
    return secrets.compare_digest(
        stored.decode() if isinstance(stored, bytes) else stored,
        provided_code,
    )


# ---------------------------------------------------------------------------
# FIDO2 / WebAuthn (py_webauthn)
# ---------------------------------------------------------------------------

_FIDO2_REG_PREFIX = "fido2:reg_challenge:"
_FIDO2_AUTH_PREFIX = "fido2:auth_challenge:"


async def begin_fido2_registration(
    redis: aioredis.Redis,
    user_id: str,
    email: str,
    existing_credentials: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate WebAuthn registration options and cache the challenge."""
    from webauthn import generate_registration_options
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=base64.b64decode(c["credential_id"] + "=="))
        for c in existing_credentials
    ]

    options = generate_registration_options(
        rp_id=settings.MFA_WEBAUTHN_RP_ID,
        rp_name=settings.MFA_WEBAUTHN_RP_NAME,
        user_id=user_id.encode(),
        user_name=email,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    challenge_b64 = base64.b64encode(options.challenge).decode()
    await redis.set(
        f"{_FIDO2_REG_PREFIX}{user_id}",
        challenge_b64,
        ex=settings.MFA_WEBAUTHN_CHALLENGE_TTL,
    )

    from webauthn.helpers import options_to_json

    return cast(dict[str, Any], json.loads(options_to_json(options)))


async def complete_fido2_registration(
    redis: aioredis.Redis,
    user_id: str,
    credential_response: dict[str, Any],
) -> dict[str, Any]:
    """Verify WebAuthn registration response.  Returns credential data to persist."""
    from webauthn import verify_registration_response
    from webauthn.helpers.structs import RegistrationCredential

    raw_challenge = await redis.getdel(f"{_FIDO2_REG_PREFIX}{user_id}")
    if not raw_challenge:
        raise ValueError("No pending FIDO2 registration challenge — expired or already used")

    challenge_bytes = base64.b64decode(raw_challenge)

    credential = RegistrationCredential.parse_raw(json.dumps(credential_response))
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge_bytes,
        expected_rp_id=settings.MFA_WEBAUTHN_RP_ID,
        expected_origin=f"https://{settings.MFA_WEBAUTHN_RP_ID}",
        require_user_verification=False,
    )

    return {
        "credential_id": base64.b64encode(verification.credential_id).decode().rstrip("="),
        "public_key": verification.credential_public_key,
        "sign_count": verification.sign_count,
    }


async def begin_fido2_assertion(
    redis: aioredis.Redis,
    user_id: str,
    existing_credentials: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate WebAuthn authentication options and cache the challenge."""
    from webauthn import generate_authentication_options
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
    )

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=base64.b64decode(c["credential_id"] + "=="))
        for c in existing_credentials
    ]

    options = generate_authentication_options(
        rp_id=settings.MFA_WEBAUTHN_RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    challenge_b64 = base64.b64encode(options.challenge).decode()
    await redis.set(
        f"{_FIDO2_AUTH_PREFIX}{user_id}",
        challenge_b64,
        ex=settings.MFA_WEBAUTHN_CHALLENGE_TTL,
    )

    from webauthn.helpers import options_to_json

    return cast(dict[str, Any], json.loads(options_to_json(options)))


async def complete_fido2_assertion(
    redis: aioredis.Redis,
    user_id: str,
    credential_response: dict[str, Any],
    stored_credentials: list[dict[str, Any]],
) -> bool:
    """Verify a WebAuthn assertion.  Returns True on success, updates sign_count in caller."""
    from webauthn import verify_authentication_response
    from webauthn.helpers.structs import AuthenticationCredential

    raw_challenge = await redis.getdel(f"{_FIDO2_AUTH_PREFIX}{user_id}")
    if not raw_challenge:
        raise ValueError("No pending FIDO2 assertion challenge — expired or already used")

    challenge_bytes = base64.b64decode(raw_challenge)

    # Find the matching stored credential
    cred_id_b64 = credential_response.get("id", "")
    match = next(
        (c for c in stored_credentials if c["credential_id"] == cred_id_b64.rstrip("=")),
        None,
    )
    if match is None:
        return False

    credential = AuthenticationCredential.parse_raw(json.dumps(credential_response))
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge_bytes,
        expected_rp_id=settings.MFA_WEBAUTHN_RP_ID,
        expected_origin=f"https://{settings.MFA_WEBAUTHN_RP_ID}",
        credential_public_key=match["public_key"],
        credential_current_sign_count=match["sign_count"],
        require_user_verification=False,
    )

    # Caller is responsible for persisting updated sign_count
    match["sign_count"] = verification.new_sign_count
    return True


# ---------------------------------------------------------------------------
# OTP utilities
# ---------------------------------------------------------------------------


def is_mfa_required_role(role_names: list[str]) -> bool:
    """Return True if any of the user's roles require MFA (SRS SEC-004)."""
    required = set(settings.MFA_REQUIRED_ROLES)
    return bool(required.intersection(role_names))
