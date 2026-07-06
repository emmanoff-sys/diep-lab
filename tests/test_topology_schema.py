"""WP-006-01 topology-version schema evidence tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NETWORK_MODEL_SQL = (ROOT / "sql" / "013_network_model.sql").read_text(encoding="utf-8")
SEQ_FIX_SQL = (ROOT / "sql" / "024_topology_version_seq_fix.sql").read_text(encoding="utf-8")
AUDIT_VERSION_SQL = (ROOT / "sql" / "025_audit_network_model_version.sql").read_text(
    encoding="utf-8"
)


def test_network_model_version_registry_schema_is_present():
    sql = NETWORK_MODEL_SQL.lower()

    assert "create table if not exists network_model_versions" in sql
    assert "version      bigserial primary key" in sql
    assert "label        varchar(100) not null" in sql
    assert "created_by   varchar(100) not null default 'system'" in sql
    assert "is_current   boolean not null default false" in sql
    assert "insert into network_model_versions (version, label, description, is_current)" in sql


def test_topology_entities_reference_network_model_version():
    sql = NETWORK_MODEL_SQL.lower()

    assert "create table if not exists grid_nodes" in sql
    assert "model_version  bigint references network_model_versions(version)" in sql
    assert "create table if not exists grid_edges" in sql
    assert "model_version   bigint references network_model_versions(version)" in sql


def test_network_model_version_sequence_is_resynchronised_after_seed_record():
    sql = SEQ_FIX_SQL.lower()

    assert "setval('network_model_versions_version_seq'" in sql
    assert "select coalesce(max(version), 1) from network_model_versions" in sql


def test_audit_tables_record_active_network_model_version():
    sql = AUDIT_VERSION_SQL.lower()

    for table in (
        "flisr_events",
        "control_actions",
        "control_audit",
        "outage_cases",
        "automation_events",
    ):
        assert (
            f"alter table {table}".lower() in sql
            and "network_model_version bigint references network_model_versions(version)" in sql
        )
