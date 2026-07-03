"""Add MFA fields: mfa_secret, mfa_methods, webauthn_credentials table (WP-005-02).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03

SRS SEC-004 mandates:
  - mfa_secret: Fernet-encrypted TOTP base32 key stored per user
  - mfa_methods: list of enrolled MFA channels (totp, sms, fido2)
  - webauthn_credentials: table holding FIDO2 public key + sign_count per credential

SRS SEC-012 (data at rest): mfa_secret is encrypted before being written to this
column by the application layer (Fernet AES-128).  The column type is text; no
database-level encryption is added here beyond what the VM-level disk encryption
(WP-003-05) already provides.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extend users table with MFA columns
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("mfa_secret", sa.String(512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "mfa_methods",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
    )

    # ------------------------------------------------------------------
    # WebAuthn credentials table (FIDO2 — SEC-004)
    # ------------------------------------------------------------------
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.String(512), unique=True, nullable=False),
        sa.Column("public_key", sa.LargeBinary, nullable=False),
        sa.Column("sign_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_webauthn_user_id", "webauthn_credentials", ["user_id"])
    op.create_index(
        "ix_webauthn_credential_id", "webauthn_credentials", ["credential_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("webauthn_credentials")
    op.drop_column("users", "mfa_methods")
    op.drop_column("users", "mfa_secret")
