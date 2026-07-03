"""OAuth2 request/response schemas — PKCE (SRS SEC-001/002/003)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class GrantType(StrEnum):
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"


class ClientType(StrEnum):
    WEB = "web"
    MOBILE = "mobile"


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------


class AuthorizeRequest(BaseModel):
    """Parameters for the /authorize endpoint (PKCE — RFC 7636)."""

    response_type: str = Field(..., pattern="^code$")
    client_id: str
    redirect_uri: str
    code_challenge: str = Field(..., min_length=43, max_length=128)
    code_challenge_method: str = Field(default="S256", pattern="^S256$")
    scope: str = Field(default="openid")
    state: str | None = None


class TokenRequest(BaseModel):
    """OAuth2 token endpoint body (application/x-www-form-urlencoded)."""

    grant_type: GrantType
    # authorization_code fields
    code: str | None = None
    code_verifier: str | None = Field(default=None, min_length=43, max_length=128)
    redirect_uri: str | None = None
    client_id: str | None = None
    # refresh_token fields
    refresh_token: str | None = None
    client_type: ClientType = ClientType.WEB

    @field_validator("code_verifier")
    @classmethod
    def _verifier_charset(cls, v: str | None) -> str | None:
        import re

        if v is not None and not re.fullmatch(r"[A-Za-z0-9\-._~]+", v):
            raise ValueError("code_verifier contains invalid characters (RFC 7636 §4.1)")
        return v


class RevokeRequest(BaseModel):
    token: str
    token_type_hint: str = "refresh_token"


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str | None = None
    scope: str = "openid"


class AuthCodeResponse(BaseModel):
    """Returned by /authorize for first-party clients."""

    code: str
    state: str | None = None


class JWKSResponse(BaseModel):
    keys: list[dict[str, str]]
