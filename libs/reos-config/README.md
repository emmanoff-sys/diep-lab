# reos-config — Shared Configuration Framework (Backend)

**Authority:** WP-002-01 | LLD v2.0 §2.1.2 (`config.py` — Pydantic Settings, all env-driven) | LLD v2.0 §2.1.1 (typing mandate)

Every DAEP / RE-OS Python service subclasses `ReosBaseSettings` instead of hand-rolling
`config.py`. Missing required settings fail fast at startup, not at first use.

## Installation

```bash
pip install reos-config --index-url http://localhost:8080/simple/ --extra-index-url https://pypi.org/simple/
```

(Internal index per `ARTIFACT_REPOSITORY.md`, WP-001-11.)

## Fields

| Field | Type | Env Var | Default | Notes |
|-------|------|---------|---------|-------|
| `service_name` | `str` | `SERVICE_NAME` | — (required) | Kebab-case service identifier |
| `environment` | `Literal["local", "shared_dev", "ci", "staging", "production"]` | `ENVIRONMENT` | — (required) | Canonical set per Roadmap v1.0 §11.2 |
| `log_level` | `str` | `LOG_LEVEL` | `"INFO"` | Consumed by `reos-logging` (WP-002-03) |
| `database_url` | `PostgresDsn` | `DATABASE_URL` | — (required) | Password masked in `repr()` |
| `redis_url` | `RedisDsn` | `REDIS_URL` | — (required) | Password masked in `repr()` |
| `kafka_bootstrap_servers` | `str` | `KAFKA_BOOTSTRAP_SERVERS` | — (required) | Comma-separated `host:port` list |

**Reserved base field names** — subclasses must NOT redefine:
`service_name`, `environment`, `log_level`, `database_url`, `redis_url`,
`kafka_bootstrap_servers`. (WP-002-01 §35 risk mitigation.)

## Usage

```python
# services/my-service/src/my_service/config.py
from reos_config import ReosBaseSettings

class Settings(ReosBaseSettings):
    """my-service settings — adds service-specific fields to the shared base."""

    jwt_secret_key: str          # service-specific, required
    feature_flag_x: bool = False # service-specific, defaulted

settings = Settings()  # raises pydantic.ValidationError if required env vars missing
```

## Example `.env`

```dotenv
SERVICE_NAME=my-service
ENVIRONMENT=local
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql+asyncpg://reos:password@localhost:5432/my_service
REDIS_URL=redis://:password@localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
JWT_SECRET_KEY=local-dev-only-secret
```

`.env` is read in local development; deployed environments use real environment
variables (LLD v2.0 §2.1.2 "all env-driven"). Never commit `.env`.

## Security

`repr()`/`str()` mask the password component of `database_url` and `redis_url`
(WP-002-01 §25). Do not log settings via any other serialization path
(`model_dump()` is NOT masked — it is for programmatic use only, never logging).

## Environment enum synchronization

The environment value set is mirrored in `libs/reos-config-ts` (TypeScript) and
`libs/reos_config` (Dart) — see the comment block in `settings.py`. Change all
three together or not at all.

## Traceability

| Artifact | Source |
|----------|--------|
| `ReosBaseSettings` fields | LLD v2.0 §2.1.2, Roadmap v1.0 §11.2 (environment names) |
| Full typing | LLD v2.0 §2.1.1 |
| Vault integration | Out of scope — WP-003-13 layers on top; this library reads env/`.env` only |
