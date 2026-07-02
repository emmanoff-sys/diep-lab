from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    service_name: str = "service-name"
    debug: bool = False
    database_url: str = "postgresql+asyncpg://user:pass@localhost/service_db"
    kafka_bootstrap_servers: str = "localhost:9092"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
