from __future__ import annotations

from dataclasses import dataclass

from jose import JWTError, jwt  # type: ignore[import-untyped]

from service_name.config import get_settings
from service_name.core.exceptions import AuthorisationError

__all__ = ["JWTClaims", "decode_token"]


@dataclass(frozen=True)
class JWTClaims:
    sub: str
    role: str
    tenant_id: str


def decode_token(token: str) -> JWTClaims:
    settings = get_settings()
    try:
        payload: dict[str, str] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return JWTClaims(
            sub=payload["sub"],
            role=payload["role"],
            tenant_id=payload["tenant_id"],
        )
    except (JWTError, KeyError) as exc:
        raise AuthorisationError() from exc
