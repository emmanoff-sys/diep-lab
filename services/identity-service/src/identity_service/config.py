"""Service configuration — all values injected via env vars (ADR-008 / reos-config)."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IDENTITY_", env_file=".env", extra="ignore")

    # Service
    SERVICE_NAME: str = "identity-service"
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://...

    # Redis
    REDIS_URL: str  # redis://...

    # Vault (ADR-008 — AppRole credentials on tmpfs /run/reos/)
    VAULT_ADDR: str = "https://vault.internal:8200"
    VAULT_ROLE_ID_FILE: str = "/run/reos/identity-service/role-id"
    VAULT_SECRET_ID_FILE: str = "/run/reos/identity-service/secret-id"
    VAULT_PKI_MOUNT: str = "pki"
    VAULT_PKI_ROLE: str = "jwt-signing"
    VAULT_APPROLE_MOUNT: str = "approle"

    # JWT (SRS SEC-002 / SEC-003)
    JWT_ISSUER: str = "reos-identity"
    JWT_ACCESS_TOKEN_TTL: int = 900          # 15 minutes (SRS SEC-002)
    JWT_REFRESH_TOKEN_TTL_WEB: int = 86400   # 1 day (SRS SEC-003)
    JWT_REFRESH_TOKEN_TTL_MOBILE: int = 604800  # 7 days (SRS SEC-003)
    JWT_AUTH_CODE_TTL: int = 600             # 10 minutes, single-use

    # Key rotation — background task refreshes key before Vault cert expires
    JWT_KEY_REFRESH_BUFFER_SECONDS: int = 86400  # refresh 24h before expiry

    # Account lockout (SRS SEC-001 — 5-failure Redis lockout, 30-minute window)
    LOCKOUT_MAX_FAILURES: int = 5
    LOCKOUT_TTL_SECONDS: int = 1800

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_USER_EVENTS_TOPIC: str = "user.registered"

    @field_validator("DATABASE_URL")
    @classmethod
    def _require_asyncpg(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return v


settings = Settings()  # type: ignore[call-arg]
