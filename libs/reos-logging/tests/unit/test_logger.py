"""Unit tests for reos_logging — WP-002-03 §29.

Covers:
* JSON output is valid, parseable JSON (non-local environments)
* redaction processor masks sensitive fields (default + extended list)
* local environment produces human-readable (non-JSON) console output
* service_name/environment are bound into every line
* log_level filtering honours settings
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import structlog

from reos_config import ReosBaseSettings
from reos_logging import DEFAULT_REDACTED_FIELDS, configure_logging, get_logger

BASE_ENV: dict[str, str] = {
    "service_name": "log-test-service",
    "environment": "ci",
    "database_url": "postgresql+asyncpg://u:pw@db:5432/d",
    "redis_url": "redis://cache:6379/0",
    "kafka_bootstrap_servers": "kafka:9092",
}


def make_settings(**overrides: str) -> ReosBaseSettings:
    return ReosBaseSettings(_env_file=None, **{**BASE_ENV, **overrides})  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def reset_structlog() -> Any:
    yield
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def capture_output(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out.strip()


class TestJsonOutput:
    def test_non_local_env_emits_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings(environment="ci"))
        get_logger("test").info("unit.test_event", answer=42)
        parsed = json.loads(capture_output(capsys))
        assert parsed["event"] == "unit.test_event"
        assert parsed["answer"] == 42

    def test_json_line_contains_service_context_and_metadata(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(make_settings(environment="staging"))
        get_logger("test").warning("request.error", code="NOT_FOUND", status=404)
        parsed = json.loads(capture_output(capsys))
        assert parsed["service_name"] == "log-test-service"
        assert parsed["environment"] == "staging"
        assert parsed["level"] == "warning"
        assert "timestamp" in parsed
        assert parsed["code"] == "NOT_FOUND"
        assert parsed["status"] == 404


class TestRedaction:
    @pytest.mark.parametrize("field", sorted(DEFAULT_REDACTED_FIELDS))
    def test_default_sensitive_fields_masked(
        self, capsys: pytest.CaptureFixture[str], field: str
    ) -> None:
        configure_logging(make_settings())
        get_logger("test").info("auth.event", **{field: "super-secret-value"})
        out = capture_output(capsys)
        assert "super-secret-value" not in out
        assert "***REDACTED***" in out

    def test_case_insensitive_redaction(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings())
        get_logger("test").info("auth.event", Authorization="Bearer abc123")
        out = capture_output(capsys)
        assert "abc123" not in out

    def test_extra_redacted_fields_extension(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings(), extra_redacted_fields=["api_key"])
        get_logger("test").info("vendor.call", api_key="k-123456")
        out = capture_output(capsys)
        assert "k-123456" not in out

    def test_non_sensitive_fields_untouched(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings())
        get_logger("test").info("meter.read", meter_id="MTR-9")
        parsed = json.loads(capture_output(capsys))
        assert parsed["meter_id"] == "MTR-9"


class TestLocalConsoleRenderer:
    def test_local_env_output_is_not_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings(environment="local"))
        get_logger("test").info("unit.console_event")
        out = capture_output(capsys)
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
        assert "unit.console_event" in out

    def test_local_env_still_redacts(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings(environment="local"))
        get_logger("test").info("auth.event", password="pw-clear")
        assert "pw-clear" not in capture_output(capsys)


class TestLevelFiltering:
    def test_debug_suppressed_at_info_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings(log_level="INFO"))
        get_logger("test").debug("unit.debug_event")
        assert capture_output(capsys) == ""

    def test_debug_emitted_at_debug_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(make_settings(log_level="DEBUG"))
        get_logger("test").debug("unit.debug_event")
        assert "unit.debug_event" in capture_output(capsys)


class TestRequestIdBinding:
    def test_bound_request_id_appears_in_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(make_settings())
        structlog.contextvars.bind_contextvars(request_id="req-abc-123")
        get_logger("test").info("request.handled")
        parsed = json.loads(capture_output(capsys))
        assert parsed["request_id"] == "req-abc-123"
