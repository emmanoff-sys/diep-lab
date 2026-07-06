from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MASK = "*" * 3
MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/release2/db_validation_substrate.py"
SPEC = importlib.util.spec_from_file_location("db_validation_substrate", MODULE_PATH)
assert SPEC is not None
db_validation_substrate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = db_validation_substrate
SPEC.loader.exec_module(db_validation_substrate)


def test_db_config_public_identity_masks_password(monkeypatch):
    dsn = "postgresql://validator:secret@db.example:15432/release2"  # noqa: S105
    monkeypatch.setenv("DB_DSN", dsn)

    config = db_validation_substrate.DbConfig.from_env()

    assert config.connect_kwargs()["password"] == dsn.split(":", maxsplit=2)[2].split("@")[0]
    assert config.public_identity() == {
        "host": "db.example",
        "port": 15432,
        "dbname": "release2",
        "user": "validator",
        "password": MASK,
    }


def test_db_config_uses_legacy_parts_when_dsn_absent(monkeypatch):
    monkeypatch.delenv("DB_DSN", raising=False)
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_PORT", "15432")
    monkeypatch.setenv("DB_NAME", "release2")
    monkeypatch.setenv("DB_USER", "validator")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    config = db_validation_substrate.DbConfig.from_env()

    assert config.dsn() == "postgresql://validator:secret@db.example:15432/release2"


def test_compatibility_env_derives_service_aliases_from_db_dsn(monkeypatch):
    monkeypatch.setenv("DB_DSN", "postgresql://validator:secret@localhost:5432/release2")

    config = db_validation_substrate.DbConfig.from_env()

    assert config.compatibility_env() == {
        "DB_DSN": "postgresql://validator:secret@localhost:5432/release2",
        "AUDIT_DB_DSN": "postgresql+asyncpg://validator:secret@localhost:5432/release2",
        "DATABASE_URL": "postgresql+asyncpg://validator:secret@localhost:5432/release2",
        "IDENTITY_DATABASE_URL": "postgresql+asyncpg://validator:secret@localhost:5432/release2",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "release2",
        "DB_USER": "validator",
        "DB_PASSWORD": "secret",
    }


def test_write_github_env_file_masks_only_public_output(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_DSN", "postgresql://validator:secret@localhost:5432/release2")
    output = tmp_path / "github.env"
    config = db_validation_substrate.DbConfig.from_env()

    db_validation_substrate.write_env_file(config, output, "github")

    text = output.read_text(encoding="utf-8")
    assert "DB_DSN=postgresql://validator:secret@localhost:5432/release2" in text
    assert "AUDIT_DB_DSN=postgresql+asyncpg://validator:secret@localhost:5432/release2" in text
    assert config.public_compatibility_env()["DB_PASSWORD"] == MASK


def test_migration_files_are_sorted(tmp_path):
    (tmp_path / "010_later.sql").write_text("SELECT 10;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not sql", encoding="utf-8")

    files = db_validation_substrate.migration_files(tmp_path)

    assert [path.name for path in files] == ["001_first.sql", "010_later.sql"]


def test_emit_writes_jsonl(tmp_path, capsys):
    output = tmp_path / "evidence.jsonl"

    db_validation_substrate.emit("database_ready", output, host="localhost")

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "event": "database_ready",
        "host": "localhost",
    }
    assert '"event": "database_ready"' in capsys.readouterr().out
