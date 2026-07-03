"""Unit tests — RS256 JWT issuance and JWKS generation (SRS SEC-002).

Uses an in-memory RSA key pair (no Vault dependency).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jose import jwt as jose_jwt


def _generate_rsa_pair() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


@pytest.fixture
def jwt_mgr_with_key(rsa_key_pair: tuple[bytes, bytes]) -> object:
    from identity_service.core.jwt import JWTManager

    mgr = JWTManager()
    priv_pem, pub_pem = rsa_key_pair
    mgr._private_key_pem = priv_pem

    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from identity_service.core.jwt import _rsa_public_key_to_jwk

    pub_key: RSAPublicKey = load_pem_public_key(pub_pem)  # type: ignore[assignment]
    mgr._kid = "test-key-v1"
    mgr._jwks = [_rsa_public_key_to_jwk(pub_key, "test-key-v1")]
    return mgr


def test_create_access_token_is_rs256(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    user_id = uuid4()
    token = mgr.create_access_token(subject=user_id, roles=["customer"], permissions=["own:read"])

    header = jose_jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    assert header["kid"] == "test-key-v1"


def test_access_token_claims(jwt_mgr_with_key: object, rsa_key_pair: tuple[bytes, bytes]) -> None:
    from identity_service.core.jwt import JWTManager
    from identity_service.config import settings

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    user_id = uuid4()
    _, pub_pem = rsa_key_pair
    token = mgr.create_access_token(
        subject=user_id, roles=["customer", "readonly"], permissions=["own:read", "energy:read"]
    )

    claims = jose_jwt.decode(
        token,
        pub_pem.decode(),
        algorithms=["RS256"],
        audience="reos",
    )
    assert claims["sub"] == str(user_id)
    assert claims["iss"] == settings.JWT_ISSUER
    assert claims["roles"] == ["customer", "readonly"]
    assert "own:read" in claims["permissions"]
    assert "jti" in claims
    assert claims["exp"] - claims["iat"] == settings.JWT_ACCESS_TOKEN_TTL


def test_access_token_ttl(jwt_mgr_with_key: object, rsa_key_pair: tuple[bytes, bytes]) -> None:
    from identity_service.core.jwt import JWTManager
    from identity_service.config import settings

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    _, pub_pem = rsa_key_pair
    token = mgr.create_access_token(subject=uuid4(), roles=[], permissions=[])
    claims = jose_jwt.decode(token, pub_pem.decode(), algorithms=["RS256"], audience="reos")
    assert claims["exp"] - claims["iat"] == 900  # SRS SEC-002: 900s ATT


def test_refresh_token_is_unique(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    tokens = {mgr.create_refresh_token() for _ in range(50)}
    assert len(tokens) == 50


def test_jwks_contains_rsa_public_key(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    jwks = mgr.get_jwks()
    assert len(jwks) == 1
    key = jwks[0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert "n" in key
    assert "e" in key
    assert key["kid"] == "test-key-v1"


def test_uninitialised_manager_raises() -> None:
    from identity_service.core.jwt import JWTManager

    mgr = JWTManager()
    with pytest.raises(RuntimeError, match="not initialised"):
        mgr.create_access_token(subject=uuid4(), roles=[], permissions=[])
