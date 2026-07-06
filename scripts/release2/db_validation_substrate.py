#!/usr/bin/env python3
"""Release 2 database validation substrate.

This helper is release-engineering support. It provides a single database
readiness and migration path for local and CI validation without relying on
host-installed `psql` or `pg_isready`.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATION_DIR = ROOT / "sql"


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    name: str
    user: str
    password: str
    scheme: str = "postgresql"

    @classmethod
    def from_env(cls) -> DbConfig:
        dsn = os.getenv("DB_DSN")
        if dsn:
            return cls.from_dsn(dsn)
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            name=os.getenv("DB_NAME", "diep"),
            user=os.getenv("DB_USER", "diep"),
            password=os.getenv("DB_PASSWORD", "diep123"),
        )

    @classmethod
    def from_dsn(cls, dsn: str) -> DbConfig:
        parsed = urlsplit(dsn)
        if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
            raise SystemExit("DB_DSN must use postgresql:// or postgresql+asyncpg://")
        if not parsed.hostname or not parsed.path.lstrip("/"):
            raise SystemExit("DB_DSN must include host and database name")
        return cls(
            host=parsed.hostname,
            port=parsed.port or 5432,
            name=unquote(parsed.path.lstrip("/")),
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            scheme=parsed.scheme,
        )

    def connect_kwargs(self) -> dict[str, str | int]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
        }

    def public_identity(self) -> dict[str, str | int]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": "***",
        }

    def dsn(self, scheme: str = "postgresql") -> str:
        credentials = quote(self.user)
        if self.password:
            credentials = f"{credentials}:{quote(self.password)}"
        netloc = (
            f"{credentials}@{self.host}:{self.port}" if credentials else f"{self.host}:{self.port}"
        )
        return urlunsplit((scheme, netloc, f"/{quote(self.name)}", "", ""))

    def public_dsn(self, scheme: str = "postgresql") -> str:
        netloc = (
            f"{quote(self.user)}:***@{self.host}:{self.port}"
            if self.user
            else f"{self.host}:{self.port}"
        )
        return urlunsplit((scheme, netloc, f"/{quote(self.name)}", "", ""))

    def compatibility_env(self) -> dict[str, str]:
        sync_dsn = self.dsn("postgresql")
        async_dsn = self.dsn("postgresql+asyncpg")
        return {
            "DB_DSN": sync_dsn,
            "AUDIT_DB_DSN": async_dsn,
            "DATABASE_URL": async_dsn,
            "IDENTITY_DATABASE_URL": async_dsn,
            "DB_HOST": self.host,
            "DB_PORT": str(self.port),
            "DB_NAME": self.name,
            "DB_USER": self.user,
            "DB_PASSWORD": self.password,
        }

    def public_compatibility_env(self) -> dict[str, str]:
        public_sync_dsn = self.public_dsn("postgresql")
        public_async_dsn = self.public_dsn("postgresql+asyncpg")
        env = self.compatibility_env()
        env.update(
            {
                "DB_DSN": public_sync_dsn,
                "AUDIT_DB_DSN": public_async_dsn,
                "DATABASE_URL": public_async_dsn,
                "IDENTITY_DATABASE_URL": public_async_dsn,
                "DB_PASSWORD": "***",
            }
        )
        return env


def migration_files(migration_dir: Path = DEFAULT_MIGRATION_DIR) -> list[Path]:
    return sorted(path for path in migration_dir.glob("*.sql") if path.is_file())


def emit(event: str, output: Path | None = None, **fields: object) -> None:
    record = {"event": event, **fields}
    line = json.dumps(record, sort_keys=True)
    print(line)
    if output is not None:
        with output.open("a", encoding="utf-8") as fh:
            fh.write(f"{line}\n")


def write_env_file(config: DbConfig, output: Path, env_format: str) -> None:
    env = config.compatibility_env()
    output.parent.mkdir(parents=True, exist_ok=True)
    if env_format == "github":
        output.write_text(
            "".join(f"{key}={value}\n" for key, value in env.items()), encoding="utf-8"
        )
        return
    if env_format == "shell":
        lines = [f"export {key}={quote_shell(value)}\n" for key, value in env.items()]
        output.write_text("".join(lines), encoding="utf-8")
        return
    if env_format == "json":
        output.write_text(json.dumps(env, sort_keys=True, indent=2), encoding="utf-8")
        return
    raise SystemExit(f"unsupported env format: {env_format}")


def quote_shell(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def psycopg2_module() -> Any:
    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "psycopg2 is required for Release 2 database validation; "
            "install psycopg2-binary in the validation environment"
        ) from exc
    return psycopg2


def wait_for_database(config: DbConfig, timeout_seconds: int, output: Path | None = None) -> Any:
    psycopg2 = psycopg2_module()
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            conn = psycopg2.connect(**config.connect_kwargs())
            conn.autocommit = True
            emit("database_ready", output, database=config.public_identity())
            return conn
        except Exception as exc:  # noqa: BLE001 - all connection failures are retryable here.
            last_error = exc
            time.sleep(1)

    emit(
        "database_unavailable",
        output,
        database=config.public_identity(),
        error=str(last_error),
        timeout_seconds=timeout_seconds,
    )
    raise SystemExit(1)


def validate_timescaledb(conn: Any, output: Path | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
        row = cur.fetchone()
    if row is None:
        emit("timescaledb_extension_missing", output)
        raise SystemExit(1)
    emit("timescaledb_extension_present", output)


def apply_migration(conn: Any, path: Path, output: Path | None = None) -> None:
    emit("migration_start", output, path=path.as_posix())
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    emit("migration_complete", output, path=path.as_posix())


def run_check(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("", encoding="utf-8")
    config = DbConfig.from_env()
    with wait_for_database(config, args.timeout, output) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
        emit("database_version", output, version=version)
    return 0


def run_migrate(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("", encoding="utf-8")

    files = migration_files(Path(args.migration_dir))
    if not files:
        emit("migration_set_empty", output, migration_dir=args.migration_dir)
        raise SystemExit(1)

    emit("migration_set", output, count=len(files), paths=[path.as_posix() for path in files])
    if args.dry_run:
        return 0

    config = DbConfig.from_env()
    with wait_for_database(config, args.timeout, output) as conn:
        for path in files:
            apply_migration(conn, path, output)
        if args.require_timescaledb:
            validate_timescaledb(conn, output)
    return 0


def run_env(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    config = DbConfig.from_env()
    if output is not None:
        write_env_file(config, output, args.format)
    emit(
        "db_env_contract",
        None,
        format=args.format,
        output_path=output.as_posix() if output else None,
        env=config.public_compatibility_env(),
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Release 2 database validation substrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="validate DB connectivity")
    check.add_argument("--timeout", type=int, default=60)
    check.add_argument("--output", help="write JSONL evidence to this path")
    check.set_defaults(func=run_check)

    migrate = subparsers.add_parser("migrate", help="apply SQL migrations")
    migrate.add_argument("--migration-dir", default=DEFAULT_MIGRATION_DIR.as_posix())
    migrate.add_argument("--timeout", type=int, default=60)
    migrate.add_argument("--output", help="write JSONL evidence to this path")
    migrate.add_argument("--dry-run", action="store_true", help="list migrations without DB access")
    migrate.add_argument(
        "--require-timescaledb",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="require the TimescaleDB extension after migrations",
    )
    migrate.set_defaults(func=run_migrate)

    env = subparsers.add_parser("env", help="emit DB_DSN-derived compatibility environment")
    env.add_argument("--format", choices=["github", "shell", "json"], default="shell")
    env.add_argument("--output", help="write env contract to this file")
    env.set_defaults(func=run_env)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
