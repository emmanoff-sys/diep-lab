"""Unit tests — JWT decode (JWTManager.decode_access_token, SRS SEC-002)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from identity_service.core.jwt import _rsa_public_key_to_jwk


@pytest.fixture
def jwt_mgr_with_key(rsa_key_pair: tuple[bytes, bytes]) -> object:
    from identity_service.core.jwt import JWTManager

    priv_pem, pub_pem = rsa_key_pair
    mgr = JWTManager()
    mgr._private_key_pem = priv_pem
    mgr._public_key_pem = pub_pem

    pub_key: RSAPublicKey = load_pem_public_key(pub_pem)  # type: ignore[assignment]
    mgr._kid = "test-key-v1"
    mgr._jwks = [_rsa_public_key_to_jwk(pub_key, "test-key-v1")]
    return mgr


def test_decode_valid_token(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    user_id = uuid4()
    token = mgr.create_access_token(subject=user_id, roles=["customer"], permissions=["own:read"])
    payload = mgr.decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["iss"] == "reos-identity"
    assert payload["aud"] == "reos"
    assert "jti" in payload


def test_decode_rejects_invalid_signature(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    token = mgr.create_access_token(subject=uuid4(), roles=[], permissions=[])
    header, body, _ = token.split(".")
    tampered = f"{header}.{body}.invalidsignatureXXXXXXXXX"
    with pytest.raises(ValueError):
        mgr.decode_access_token(tampered)


def test_decode_rejects_garbage(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    with pytest.raises(ValueError):
        mgr.decode_access_token("not.a.valid.jwt")


def test_decode_uninitialised_raises() -> None:
    from identity_service.core.jwt import JWTManager

    mgr = JWTManager()
    with pytest.raises(RuntimeError, match="not initialised"):
        mgr.decode_access_token("any.token.here")


def test_decode_preserves_roles_and_permissions(jwt_mgr_with_key: object) -> None:
    from identity_service.core.jwt import JWTManager

    mgr: JWTManager = jwt_mgr_with_key  # type: ignore[assignment]
    roles = ["customer", "readonly"]
    perms = ["own:read", "energy:read"]
    token = mgr.create_access_token(subject=uuid4(), roles=roles, permissions=perms)
    payload = mgr.decode_access_token(token)
    assert payload["roles"] == roles
    assert payload["permissions"] == perms
