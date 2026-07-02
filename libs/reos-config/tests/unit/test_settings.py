"""Unit tests for reos_config.settings — WP-002-01 §29.

Covers:
* missing required field raises ``ValidationError``
* valid environment values load correctly
* ``environment`` rejects values outside the Literal set
* masked ``__repr__`` never exposes a password substring
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reos_config.settings import ReosBaseSettings, _mask_dsn

VALID_ENV: dict[str, str] = {
    "service_name": "test-service",
    "environment": "local",
    "database_url": "postgresql+asyncpg://reos:s3cretpw@db.internal:5432/reos",
    "redis_url": "redis://:redispw123@cache.internal:6379/0",
    "kafka_bootstrap_servers": "kafka.internal:9092",
}


def _settings(**overrides: str) -> ReosBaseSettings:
    values = {**VALID_ENV, **overrides}
    return ReosBaseSettings(_env_file=None, **values)  # type: ignore[arg-type]


class TestRequiredFields:
    def test_missing_required_field_raises_validation_error(self) -> None:
        values = {k: v for k, v in VALID_ENV.items() if k != "database_url"}
        with pytest.raises(ValidationError) as excinfo:
            ReosBaseSettings(_env_file=None, **values)  # type: ignore[arg-type]
        assert "database_url" in str(excinfo.value)

    def test_all_required_fields_missing_lists_every_field(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            ReosBaseSettings(_env_file=None)
        message = str(excinfo.value)
        for field in (
            "service_name",
            "environment",
            "database_url",
            "redis_url",
            "kafka_bootstrap_servers",
        ):
            assert field in message


class TestValidLoad:
    def test_valid_values_load(self) -> None:
        settings = _settings()
        assert settings.service_name == "test-service"
        assert settings.environment == "local"
        assert settings.log_level == "INFO"
        assert settings.kafka_bootstrap_servers == "kafka.internal:9092"

    def test_log_level_default_overridable(self) -> None:
        settings = _settings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"

    @pytest.mark.parametrize("env", ["local", "shared_dev", "ci", "staging", "production"])
    def test_every_canonical_environment_accepted(self, env: str) -> None:
        settings = _settings(environment=env)
        assert settings.environment == env


class TestEnvironmentLiteral:
    @pytest.mark.parametrize("env", ["dev", "prod", "LOCAL", "test", ""])
    def test_environment_outside_literal_set_rejected(self, env: str) -> None:
        with pytest.raises(ValidationError):
            _settings(environment=env)


class TestMaskedRepr:
    def test_repr_never_contains_database_password(self) -> None:
        settings = _settings()
        assert "s3cretpw" not in repr(settings)
        assert "s3cretpw" not in str(settings)

    def test_repr_never_contains_redis_password(self) -> None:
        settings = _settings()
        assert "redispw123" not in repr(settings)

    def test_repr_still_shows_host_and_user(self) -> None:
        rendered = repr(settings := _settings())
        assert settings is not None
        assert "db.internal" in rendered
        assert "reos" in rendered

    def test_mask_dsn_without_password_unchanged(self) -> None:
        dsn = "postgresql://db.internal:5432/reos"
        assert _mask_dsn(dsn) == dsn

    def test_mask_dsn_masks_only_password(self) -> None:
        masked = _mask_dsn("redis://user:topsecret@host:6379/0")
        assert masked == "redis://user:***@host:6379/0"

    def test_mask_dsn_user_without_password_unchanged(self) -> None:
        dsn = "redis://user@host:6379/0"
        assert _mask_dsn(dsn) == dsn
