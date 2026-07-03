"""RS256 JWT issuance + JWKS generation (SRS SEC-002).

Key lifecycle:
  - On startup: fetch RSA-4096 key from Vault PKI (30-day cert)
  - Background task: refresh key when cert expiry < JWT_KEY_REFRESH_BUFFER_SECONDS away
  - JWKS: public key exposed at /api/v1/jwks as RFC 7517 JWK Set

JWT claims (access token):
  iss, sub, aud, iat, exp (900s), jti, roles[], permissions[]
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate
from jose import JWTError, jwt

from identity_service.config import settings
from identity_service.core.vault import VaultClient

logger = logging.getLogger(__name__)


def _rsa_public_key_to_jwk(public_key: RSAPublicKey, kid: str) -> dict[str, str]:
    """Convert RSA public key to RFC 7517 JWK object."""
    numbers = public_key.public_numbers()
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode(),
        "e": base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode(),
    }


class JWTManager:
    """Holds the current RS256 signing key and issues/verifies JWTs."""

    def __init__(self) -> None:
        self._private_key_pem: bytes | None = None
        self._public_key_pem: bytes | None = None
        self._jwks: list[dict[str, str]] = []
        self._kid: str = ""
        self._cert_expiry: datetime | None = None
        self._vault: VaultClient | None = None
        self._refresh_task: asyncio.Task[None] | None = None

    async def initialise(self, vault: VaultClient) -> None:
        self._vault = vault
        await self._fetch_key()
        self._refresh_task = asyncio.create_task(self._key_refresh_loop())

    async def _fetch_key(self) -> None:
        assert self._vault is not None
        material = await self._vault.issue_jwt_signing_key()

        self._private_key_pem = material["private_key"].encode()

        cert = load_pem_x509_certificate(material["certificate"].encode())
        public_key: RSAPublicKey = cert.public_key()  # type: ignore[assignment]
        self._cert_expiry = cert.not_valid_after_utc

        self._public_key_pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        serial = material["serial_number"].replace(":", "")[:16]
        self._kid = f"v1-{serial}"

        self._jwks = [_rsa_public_key_to_jwk(public_key, self._kid)]
        logger.info("jwt.key_loaded", kid=self._kid, expires=self._cert_expiry.isoformat())

    async def _key_refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(3600)  # check every hour
            if self._cert_expiry is None:
                continue
            remaining = (self._cert_expiry - datetime.now(UTC)).total_seconds()
            if remaining < settings.JWT_KEY_REFRESH_BUFFER_SECONDS:
                logger.info("jwt.key_rotating", remaining_seconds=remaining)
                try:
                    await self._fetch_key()
                except Exception:
                    logger.exception("jwt.key_rotation_failed")

    def create_access_token(
        self,
        subject: UUID,
        roles: list[str],
        permissions: list[str],
        audience: str = "reos",
    ) -> str:
        if not self._private_key_pem:
            raise RuntimeError("JWTManager not initialised")
        now = datetime.now(UTC)
        payload: dict[str, object] = {
            "iss": settings.JWT_ISSUER,
            "sub": str(subject),
            "aud": audience,
            "iat": now,
            "exp": now + timedelta(seconds=settings.JWT_ACCESS_TOKEN_TTL),
            "jti": str(uuid4()),
            "roles": roles,
            "permissions": permissions,
        }
        return jwt.encode(
            payload,
            self._private_key_pem.decode(),
            algorithm="RS256",
            headers={"kid": self._kid},
        )

    def decode_access_token(self, token: str, audience: str = "reos") -> dict[str, object]:
        """Validate an RS256 Bearer token and return its claims (SRS SEC-002).

        Raises ValueError on any validation failure (expired, bad sig, wrong aud, etc.).
        Never accepts HS256 — algorithm is pinned to RS256.
        """
        if not self._public_key_pem:
            raise RuntimeError("JWTManager not initialised")
        try:
            return jwt.decode(  # type: ignore[return-value]
                token,
                self._public_key_pem.decode(),
                algorithms=["RS256"],
                audience=audience,
            )
        except JWTError as exc:
            raise ValueError(str(exc)) from exc

    def create_mfa_pending_token(self, subject: UUID, token_type: str = "mfa-pending") -> str:
        """Issue a short-lived intermediate token for the MFA verification step (SEC-004).

        token_type values:
          "mfa-pending"        — user has MFA enrolled, must verify before receiving full tokens
          "mfa-setup-required" — privileged user must enrol MFA before receiving full tokens

        Audience is "reos-mfa" (distinct from the "reos" access-token audience) so that
        this token cannot be used as an access token on other services.
        """
        if not self._private_key_pem:
            raise RuntimeError("JWTManager not initialised")
        now = datetime.now(UTC)
        ttl = (
            settings.MFA_SETUP_TOKEN_TTL
            if token_type == "mfa-setup-required"
            else settings.MFA_PENDING_TOKEN_TTL
        )
        payload: dict[str, object] = {
            "iss": settings.JWT_ISSUER,
            "sub": str(subject),
            "aud": "reos-mfa",
            "iat": now,
            "exp": now + timedelta(seconds=ttl),
            "jti": str(uuid4()),
            "type": token_type,
        }
        return jwt.encode(
            payload,
            self._private_key_pem.decode(),
            algorithm="RS256",
            headers={"kid": self._kid},
        )

    def decode_mfa_pending_token(
        self,
        token: str,
        expected_type: str | None = None,
    ) -> dict[str, object]:
        """Validate an MFA intermediate token and return its claims.

        Raises ValueError on any validation failure.
        Raises RuntimeError if the JWTManager is not initialised.
        """
        if not self._public_key_pem:
            raise RuntimeError("JWTManager not initialised")
        try:
            claims: dict[str, object] = jwt.decode(
                token,
                self._public_key_pem.decode(),
                algorithms=["RS256"],
                audience="reos-mfa",
            )  # type: ignore[assignment]
        except JWTError as exc:
            raise ValueError(str(exc)) from exc
        if expected_type is not None and claims.get("type") != expected_type:
            raise ValueError(
                f"Token type mismatch: expected {expected_type!r}, got {claims.get('type')!r}"
            )
        return claims

    def create_refresh_token(self) -> str:
        """Opaque, cryptographically-secure refresh token (stored hash in Redis)."""
        return secrets.token_urlsafe(48)

    def get_jwks(self) -> list[dict[str, str]]:
        return list(self._jwks)

    async def close(self) -> None:
        if self._refresh_task:
            self._refresh_task.cancel()


# Module-level singleton — initialised in lifespan
jwt_manager = JWTManager()
