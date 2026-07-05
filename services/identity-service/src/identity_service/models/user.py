"""User ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from identity_service.models.base import Base
from identity_service.models.role import user_roles
from sqlalchemy import Boolean, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # mfa_secret: Fernet-encrypted TOTP base32 secret (SEC-012 at-rest encryption)
    mfa_secret: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    # mfa_methods: list of enrolled MFA methods e.g. ["totp", "fido2"]
    mfa_methods: Mapped[list[str]] = mapped_column(
        ARRAY(sa.String),
        nullable=False,
        server_default=sa.text("ARRAY[]::text[]"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    roles: Mapped[list[Any]] = relationship(
        "Role", secondary=user_roles, back_populates="users", lazy="selectin"
    )
    webauthn_credentials: Mapped[list[Any]] = relationship(
        "WebAuthnCredential", back_populates="user", cascade="all, delete-orphan"
    )
