"""Create audit schema, hypertable, retention, immutability trigger, chain_state.

Revision ID: 0001
Revises:
Create Date: 2026-07-04

ENG-SPEC-005-04 §9.1 — Full DDL as approved in AR-051 (96/100 APPROVED).
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


def upgrade() -> None:
    # Step 1: Schema
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    # Step 2: Main events table
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("actor_type", sa.Text, nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_username", sa.Text, nullable=True),
        sa.Column("actor_ip_address", postgresql.INET, nullable=True),
        sa.Column("actor_user_agent", sa.Text, nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("resource_type", sa.Text, nullable=False),
        sa.Column("resource_id", sa.Text, nullable=True),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("outcome_reason", sa.Text, nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Text, nullable=True),
        sa.Column("service_name", sa.Text, nullable=False),
        sa.Column("service_version", sa.Text, nullable=True),
        sa.Column("prev_event_hash", sa.Text, nullable=True),
        sa.Column("event_hash", sa.Text, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("timestamp_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "ingested_at_utc",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("schema_version", sa.SMALLINT, nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id", "timestamp_utc"),
        sa.CheckConstraint(
            "actor_type IN ('user','service','system')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('success','failure','denied')",
            name="ck_audit_events_outcome",
        ),
        schema="audit",
    )

    # Step 3: Unique constraint for idempotency (AUD-FR-014)
    op.create_unique_constraint(
        "uq_audit_events_event_id",
        "audit_events",
        ["event_id"],
        schema="audit",
    )

    # Step 4: Indexes (ENG-SPEC-005-04 §9.1)
    op.create_index(
        "ix_audit_events_actor_id",
        "audit_events",
        ["actor_id", "timestamp_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_events_event_type",
        "audit_events",
        ["event_type", "timestamp_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_events_resource",
        "audit_events",
        ["resource_type", "resource_id", "timestamp_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_events_correlation_id",
        "audit_events",
        ["correlation_id"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_events_outcome",
        "audit_events",
        ["outcome", "timestamp_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_events_service_name",
        "audit_events",
        ["service_name", "timestamp_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_events_metadata",
        "audit_events",
        ["metadata"],
        postgresql_using="gin",
        schema="audit",
    )

    # Step 5: TimescaleDB hypertable (1-month chunks)
    op.execute(
        "SELECT create_hypertable("
        "  'audit.audit_events', 'timestamp_utc',"
        "  chunk_time_interval => INTERVAL '1 month'"
        ")"
    )

    # Step 6: Retention policy (7 years = 84 months; AUD-COMP-001)
    op.execute("SELECT add_retention_policy('audit.audit_events', INTERVAL '84 months')")

    # Step 7: Compression (after 7 days; AUD-COMP-001 / §14.1)
    op.execute(
        "ALTER TABLE audit.audit_events SET ("
        "  timescaledb.compress,"
        "  timescaledb.compress_segmentby = 'actor_id',"
        "  timescaledb.compress_orderby = 'timestamp_utc DESC'"
        ")"
    )
    op.execute("SELECT add_compression_policy('audit.audit_events', INTERVAL '7 days')")

    # Step 8: Immutability trigger function (AUD-SEC-001 / AUD-FR-005)
    op.execute("""
        CREATE OR REPLACE FUNCTION audit.prevent_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_events is append-only: UPDATE and DELETE are permanently prohibited. '
                'Raise a programme ECR if PII anonymisation requires a controlled exception.';
        END;
        $$
        """)

    # Step 9: Immutability trigger
    op.execute("""
        CREATE TRIGGER tg_audit_events_immutable
            BEFORE UPDATE OR DELETE ON audit.audit_events
            FOR EACH ROW EXECUTE FUNCTION audit.prevent_mutation()
        """)

    # Step 10: Chain state table (§8.3)
    op.create_table(
        "chain_state",
        sa.Column("partition_type", sa.Text, nullable=False),
        sa.Column("partition_key", sa.Text, nullable=False),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_event_hash", sa.Text, nullable=False),
        sa.Column("event_count", sa.BigInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("first_event_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_event_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("partition_type", "partition_key"),
        schema="audit",
    )


def downgrade() -> None:
    # !! DESTRUCTIVE !! Drops audit.audit_events (ALL AUDIT RECORDS) and audit.chain_state.
    # Downgrade is IRREVERSIBLE. Requires explicit Project Owner authorisation.
    # Document authorisation in EECR change log before executing.
    op.execute("DROP TRIGGER IF EXISTS tg_audit_events_immutable ON audit.audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit.prevent_mutation()")
    op.drop_table("chain_state", schema="audit")
    op.drop_table("audit_events", schema="audit")
    op.execute("DROP SCHEMA IF EXISTS audit")
