"""User registration and profile schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(..., min_length=12, max_length=128)
    client_type: str = "web"

    @field_validator("password")
    @classmethod
    def _password_complexity(cls, v: str) -> str:
        import re

        errors = []
        if not re.search(r"[A-Z]", v):
            errors.append("uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("lowercase letter")
        if not re.search(r"\d", v):
            errors.append("digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            errors.append("special character")
        if errors:
            raise ValueError(f"Password missing: {', '.join(errors)}")
        return v


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    is_active: bool
    is_email_verified: bool
    roles: list[str]

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    """Direct login — used by first-party clients to initiate PKCE flow."""

    username_or_email: str
    password: str
    code_challenge: str = Field(..., min_length=43, max_length=128)
    code_challenge_method: str = Field(default="S256", pattern="^S256$")
    client_id: str
    client_type: str = "web"
