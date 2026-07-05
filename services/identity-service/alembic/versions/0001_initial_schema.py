"""Initial schema — users, roles, permissions, junctions; seed 6 system roles.

Revision ID: 0001
Revises:
Create Date: 2026-07-03

System roles (is_system=True) are immutable via the API.
All 6 roles and their permission assignments are seeded here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]

# ---------------------------------------------------------------------------
# Permission definitions — {domain}:{action} taxonomy (SRS §RBAC)
# ---------------------------------------------------------------------------
_PERMISSIONS: list[tuple[str, str, str]] = [
    # (domain, action, description)
    ("users", "read", "View user accounts"),
    ("users", "write", "Create and modify user accounts"),
    ("users", "delete", "Delete user accounts"),
    ("energy", "read", "View energy data and assessments"),
    ("energy", "write", "Create and modify energy data"),
    ("energy", "assess", "Run engineering assessments (PV/battery/cable sizing)"),
    ("quotations", "read", "View quotations"),
    ("quotations", "write", "Create and modify quotations"),
    ("quotations", "approve", "Approve quotations for customer delivery"),
    ("payments", "read", "View payment records"),
    ("payments", "write", "Initiate and manage payments"),
    ("support", "read", "View support tickets"),
    ("support", "write", "Create and update support tickets"),
    ("support", "assign", "Assign support tickets to agents"),
    ("reports", "read", "View reports"),
    ("reports", "generate", "Generate new reports"),
    ("admin", "platform", "Platform-level administration"),
    ("admin", "users", "User administration (role assignment)"),
    ("admin", "audit", "Access audit logs"),
    ("own", "read", "Access own account data"),
    ("own", "write", "Modify own account data"),
]

# ---------------------------------------------------------------------------
# System role definitions (SRS §RBAC — 6 immutable system roles)
# ---------------------------------------------------------------------------
_SYSTEM_ROLES: list[tuple[str, str]] = [
    ("super_admin", "Full system access — all permissions"),
    ("platform_admin", "Platform administration — users, roles, configuration"),
    ("energy_engineer", "Engineering assessments, PV/battery sizing, quotations"),
    ("customer_support", "Customer data read, support ticket management"),
    ("customer", "Own account and service access"),
    ("readonly", "Read-only access across permitted domains"),
]

# Role → permission slugs mapping
_ROLE_PERMISSIONS: dict[str, list[str] | str] = {
    "super_admin": "*",  # all permissions
    "platform_admin": [
        "users:read",
        "users:write",
        "users:delete",
        "energy:read",
        "quotations:read",
        "payments:read",
        "support:read",
        "reports:read",
        "reports:generate",
        "admin:platform",
        "admin:users",
        "admin:audit",
    ],
    "energy_engineer": [
        "energy:read",
        "energy:write",
        "energy:assess",
        "quotations:read",
        "quotations:write",
        "support:read",
        "reports:read",
        "reports:generate",
    ],
    "customer_support": [
        "users:read",
        "energy:read",
        "quotations:read",
        "payments:read",
        "support:read",
        "support:write",
        "support:assign",
    ],
    "customer": [
        "own:read",
        "own:write",
        "energy:read",
        "quotations:read",
        "payments:read",
        "support:read",
        "support:write",
    ],
    "readonly": [
        "users:read",
        "energy:read",
        "quotations:read",
        "payments:read",
        "support:read",
        "reports:read",
    ],
}


def upgrade() -> None:
    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("is_email_verified", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.UniqueConstraint("domain", "action", name="uq_permission_domain_action"),
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "assigned_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # Seed data
    # ------------------------------------------------------------------
    bind = op.get_bind()

    # Insert permissions
    perm_rows = [
        {"id": _uuid(f"{d}:{a}"), "domain": d, "action": a, "description": desc}
        for d, a, desc in _PERMISSIONS
    ]
    bind.execute(
        sa.text(
            "INSERT INTO permissions (id, domain, action, description) "
            "VALUES (:id, :domain, :action, :description)"
        ),
        perm_rows,
    )

    perm_id_map = {f"{d}:{a}": _uuid(f"{d}:{a}") for d, a, _ in _PERMISSIONS}

    # Insert system roles
    role_rows = [
        {"id": _uuid(name), "name": name, "description": desc, "is_system": True}
        for name, desc in _SYSTEM_ROLES
    ]
    bind.execute(
        sa.text(
            "INSERT INTO roles (id, name, description, is_system) "
            "VALUES (:id, :name, :description, :is_system)"
        ),
        role_rows,
    )

    # Assign permissions to roles
    rp_rows: list[dict[str, object]] = []
    all_perm_ids = list(perm_id_map.values())
    for role_name, _ in _SYSTEM_ROLES:
        role_id = _uuid(role_name)
        slugs = _ROLE_PERMISSIONS[role_name]
        assigned_ids = all_perm_ids if slugs == "*" else [perm_id_map[s] for s in slugs]  # type: ignore[union-attr]
        for pid in assigned_ids:
            rp_rows.append({"role_id": role_id, "permission_id": pid})

    bind.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "VALUES (:role_id, :permission_id)"
        ),
        rp_rows,
    )


def downgrade() -> None:
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")


def _uuid(seed: str) -> str:
    """Deterministic UUID v5 from a seed string — stable across re-runs."""
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"reos.identity.{seed}"))
