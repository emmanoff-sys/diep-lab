from __future__ import annotations

from pydantic import Field, PostgresDsn, RedisDsn
from reos_config import Environment, ReosBaseSettings

__all__ = ["Settings", "get_settings"]


class Settings(ReosBaseSettings):
    """service-name settings — subclasses the shared base (WP-002-01).

    The shared base contributes: service_name, environment, log_level,
    database_url, redis_url, kafka_bootstrap_servers. Add only
    service-specific fields here.

    NOTE (template only): base fields are given local-dev defaults below so
    the scaffold starts without a .env file. When creating a real service,
    REMOVE these defaults — required settings must fail fast when unset.
    """

    service_name: str = "service-name"
    environment: Environment = "local"
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://user:pass@localhost/service_db",
        validate_default=True,
    )
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        validate_default=True,
    )
    kafka_bootstrap_servers: str = "localhost:9092"

    debug: bool = False
    jwt_secret_key: str = (
        "change-me-in-production"  # noqa: S105 — placeholder, not a real credential
    )
    jwt_algorithm: str = "HS256"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
