"""Unit tests — TOTP generation and verification (WP-005-02 / SRS SEC-004)."""

from __future__ import annotations

import pyotp
import pytest
from identity_service.core.mfa import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    get_totp_provisioning_uri,
    is_mfa_required_role,
    verify_totp,
)


def test_generate_totp_secret_is_valid_base32() -> None:
    secret = generate_totp_secret()
    assert len(secret) == 32  # pyotp random_base32 default length
    # Confirm pyotp can use it without raising
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert len(code) == 6
    assert code.isdigit()


def test_provisioning_uri_format() -> None:
    secret = generate_totp_secret()
    uri = get_totp_provisioning_uri(secret, "user@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "user%40example.com" in uri or "user@example.com" in uri
    assert "REOS" in uri


def test_verify_totp_correct_code() -> None:
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    current_code = totp.now()
    assert verify_totp(secret, current_code) is True


def test_verify_totp_wrong_code() -> None:
    secret = generate_totp_secret()
    assert verify_totp(secret, "000000") is False


def test_verify_totp_window_tolerance() -> None:
    """±1 window: codes adjacent in time should pass, codes far outside window should fail."""
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    # Code at offset +1 step should still verify with window=1
    adjacent_code = totp.at(int(totp.timecode(None)) + 1)
    assert verify_totp(secret, adjacent_code, window=1) is True


def test_verify_totp_wrong_code_outside_window() -> None:
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    # Code from 10 steps ago should fail with window=1
    old_code = totp.at(int(totp.timecode(None)) - 10)
    assert verify_totp(secret, old_code, window=1) is False


def test_encrypt_decrypt_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test mode (no encryption key): encrypt returns plaintext unchanged."""
    monkeypatch.setattr("identity_service.core.mfa._fernet", None)
    # Force test mode (empty key)
    monkeypatch.setattr("identity_service.config.settings.MFA_SECRET_ENCRYPTION_KEY", "")
    secret = generate_totp_secret()
    stored = encrypt_totp_secret(secret)
    recovered = decrypt_totp_secret(stored)
    assert recovered == secret


def test_encrypt_decrypt_with_fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a real Fernet key the encrypted ciphertext differs from plaintext."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setattr("identity_service.core.mfa._fernet", None)
    monkeypatch.setattr("identity_service.config.settings.MFA_SECRET_ENCRYPTION_KEY", key)
    secret = generate_totp_secret()
    stored = encrypt_totp_secret(secret)
    assert stored != secret  # encrypted ciphertext differs from plaintext
    recovered = decrypt_totp_secret(stored)
    assert recovered == secret


def test_is_mfa_required_role_positive() -> None:
    assert is_mfa_required_role(["customer", "energy_engineer"]) is True
    assert is_mfa_required_role(["super_admin"]) is True
    assert is_mfa_required_role(["platform_admin", "readonly"]) is True


def test_is_mfa_required_role_negative() -> None:
    assert is_mfa_required_role(["customer"]) is False
    assert is_mfa_required_role(["readonly"]) is False
    assert is_mfa_required_role([]) is False


def test_intermediate_token_creation_and_decoding() -> None:
    """JWTManager issues and decodes mfa-pending intermediate tokens."""
    import uuid

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from identity_service.core.jwt import JWTManager, _rsa_public_key_to_jwk

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    pub_key = private_key.public_key()
    pub_pem = pub_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    mgr = JWTManager()
    mgr._private_key_pem = priv_pem
    mgr._public_key_pem = pub_pem
    mgr._kid = "test-mfa-key"
    mgr._jwks = [_rsa_public_key_to_jwk(pub_key, "test-mfa-key")]

    user_id = uuid.uuid4()
    token = mgr.create_mfa_pending_token(
        user_id,
        token_type="mfa-pending",  # noqa: S106 — MFA state token type, not a credential
    )
    claims = mgr.decode_mfa_pending_token(token, expected_type="mfa-pending")

    assert claims["sub"] == str(user_id)
    assert claims["type"] == "mfa-pending"
    assert claims["aud"] == "reos-mfa"


def test_intermediate_token_type_mismatch_raises() -> None:
    """decode_mfa_pending_token raises ValueError on wrong type claim."""
    import uuid

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from identity_service.core.jwt import JWTManager, _rsa_public_key_to_jwk

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    pub_key = private_key.public_key()
    pub_pem = pub_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    mgr = JWTManager()
    mgr._private_key_pem = priv_pem
    mgr._public_key_pem = pub_pem
    mgr._kid = "test-mfa-key"
    mgr._jwks = [_rsa_public_key_to_jwk(pub_key, "test-mfa-key")]

    token = mgr.create_mfa_pending_token(
        uuid.uuid4(),
        token_type="mfa-setup-required",  # noqa: S106 — MFA state token type, not a credential
    )
    with pytest.raises(ValueError, match="type mismatch"):
        mgr.decode_mfa_pending_token(token, expected_type="mfa-pending")
