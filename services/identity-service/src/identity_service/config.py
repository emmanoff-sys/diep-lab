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

    # MFA — roles requiring MFA (SRS SEC-004)
    # Configurable so the role-name mapping from DB seed can be aligned without a code change.
    MFA_REQUIRED_ROLES: list[str] = ["energy_engineer", "platform_admin", "super_admin"]

    # MFA intermediate tokens (SRS SEC-004 — short-lived, MFA-gated)
    MFA_PENDING_TOKEN_TTL: int = 300   # 5 min — user must complete MFA within this window
    MFA_SETUP_TOKEN_TTL: int = 600     # 10 min — user must enrol MFA within this window

    # MFA lockout (SRS SEC-005 — exact values, not independently configurable without ECR)
    MFA_LOCKOUT_MAX_ATTEMPTS: int = 5       # SEC-005: lock at 5 failures
    MFA_LOCKOUT_WINDOW_SECONDS: int = 1800  # SEC-005: 30-minute attempt window (INCR TTL)
    MFA_LOCKED_TTL_SECONDS: int = 900       # SEC-005: 15-minute lock TTL

    # TOTP (SRS SEC-004 — pyotp)
    MFA_TOTP_WINDOW: int = 1           # ±1 time-step tolerance (standard; not SRS-specified)
    MFA_TOTP_ISSUER: str = "REOS"      # issuer label in otpauth:// URI

    # SMS OTP (stubbed until WP-005-05 Notification Service)
    MFA_SMS_OTP_TTL: int = 300         # 5 min for in-flight SMS OTP codes

    # FIDO2/WebAuthn (SRS SEC-004)
    MFA_WEBAUTHN_RP_ID: str = "reos.platform"
    MFA_WEBAUTHN_RP_NAME: str = "RE-OS Platform"
    MFA_WEBAUTHN_CHALLENGE_TTL: int = 300  # 5 min challenge TTL

    # TOTP secret encryption key (Fernet AES-128 — injected from Vault via env in production)
    MFA_SECRET_ENCRYPTION_KEY: str = ""  # base64url-encoded 32-byte key; empty = test mode

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
