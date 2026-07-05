"""Service configuration — all values injected via env vars (ADR-008 / reos-config)."""

from __future__ import annotations

from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuditServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_", env_file=".env", extra="ignore")

    # Service identity
    SERVICE_NAME: str = "audit-service"
    SERVICE_VERSION: str = "0.1.0"
    HOST: str = "127.0.0.1"  # default localhost; containers override via AUDIT_HOST env var
    PORT: int = 8004
    ENVIRONMENT: Literal["local", "shared_dev", "ci", "staging", "production"] = "local"

    # Database (DSN populated by vault.py at startup; override via env for local dev)
    DB_DSN: PostgresDsn
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO_SQL: bool = False

    # Vault (ADR-008 — AppRole credentials on tmpfs /run/reos/)
    VAULT_ADDR: str = "http://vault:8200"
    VAULT_ROLE_ID_PATH: str = "/run/reos/audit-service/vault-role-id"
    VAULT_SECRET_ID_PATH: str = (
        "/run/reos/audit-service/vault-secret-id"  # noqa: S105 — file path, not a credential
    )
    VAULT_DB_SECRET_PATH: str = (
        "secret/data/audit-service/db"  # noqa: S105 — Vault mount path, not a credential
    )

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_IAM_AUDIT_EVENTS_TOPIC: str = "iam.audit.events"
    KAFKA_USER_EVENTS_TOPIC: str = "user.registered"
    KAFKA_DLQ_TOPIC: str = "audit.dead.events"
    KAFKA_CONSUMER_GROUP_ID: str = "audit-service-consumer"
    KAFKA_MAX_POLL_RECORDS: int = 100
    KAFKA_SESSION_TIMEOUT_MS: int = 30_000
    KAFKA_HEARTBEAT_INTERVAL_MS: int = 10_000
    KAFKA_RETRY_MAX_ATTEMPTS: int = 3
    KAFKA_RETRY_BASE_DELAY_S: float = 1.0

    # JWT / JWKS (ENG-SPEC-005-04 §24.1)
    JWKS_URL: str = "http://identity-service:8001/api/v1/jwks"
    JWKS_CACHE_TTL_SECONDS: int = 300
    JWT_ALGORITHM: Literal["RS256"] = "RS256"
    JWT_AUDIENCE_USER: str = "reos"
    JWT_AUDIENCE_INTERNAL: str = "reos-internal"

    # Query defaults (§11.3)
    QUERY_DEFAULT_DATE_RANGE_DAYS: int = 30
    QUERY_MAX_DATE_RANGE_DAYS: int = 365
    QUERY_DEFAULT_PAGE_SIZE: int = 50
    QUERY_MAX_PAGE_SIZE: int = 200

    # Observability
    LOG_LEVEL: str = "INFO"
    METRICS_ENABLED: bool = True
    HEALTH_CHECK_TIMEOUT_S: int = 5
    # JWKS readiness: 503 if last successful fetch older than this
    JWKS_STALE_THRESHOLD_S: int = 600


settings = AuditServiceSettings()  # type: ignore[call-arg]
