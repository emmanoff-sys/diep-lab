"""Integration tests for the RFC 7807 handler — WP-002-05 §29.

A real FastAPI test app with the handler registered returns correctly shaped
RFC 7807 JSON for each of the six exception types, via a real HTTP round-trip
(TestClient). Also verifies the handler logs via reos_logging.
"""

from __future__ import annotations

import json

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reos_config import ReosBaseSettings
from reos_exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
    register_exception_handlers,
)
from reos_logging import configure_logging

RFC7807_REQUIRED_KEYS = {"type", "title", "status", "detail", "instance"}


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/validation")
    async def _validation() -> None:
        raise ValidationError("kwp must be positive", metadata={"field": "kwp"})

    @app.get("/authn")
    async def _authn() -> None:
        raise AuthenticationError()

    @app.get("/authz")
    async def _authz() -> None:
        raise AuthorizationError()

    @app.get("/missing")
    async def _missing() -> None:
        raise NotFoundError("Customer", 7)

    @app.get("/conflict")
    async def _conflict() -> None:
        raise ConflictError("version already published")

    @app.get("/upstream")
    async def _upstream() -> None:
        raise ExternalServiceError("adms", detail="timeout after 30s")

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_code"),
    [
        ("/validation", 422, "VALIDATION_ERROR"),
        ("/authn", 401, "AUTHENTICATION_REQUIRED"),
        ("/authz", 403, "AUTHORIZATION_DENIED"),
        ("/missing", 404, "RESOURCE_NOT_FOUND"),
        ("/conflict", 409, "RESOURCE_CONFLICT"),
        ("/upstream", 502, "EXTERNAL_SERVICE_ERROR"),
    ],
)
def test_each_exception_type_returns_rfc7807(
    client: TestClient, path: str, expected_status: int, expected_code: str
) -> None:
    response = client.get(path)
    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert RFC7807_REQUIRED_KEYS <= body.keys()
    assert body["status"] == expected_status
    assert body["code"] == expected_code
    assert body["instance"] == path
    assert body["type"].endswith(expected_code.lower())


def test_metadata_merged_as_extension_members(client: TestClient) -> None:
    body = client.get("/validation").json()
    assert body["field"] == "kwp"


def test_not_found_detail_shape(client: TestClient) -> None:
    body = client.get("/missing").json()
    assert body["detail"] == "Customer with id '7' was not found."
    assert body["title"] == "Customer was not found."


def test_handler_logs_via_reos_logging(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = ReosBaseSettings(
        _env_file=None,
        service_name="exc-test",
        environment="ci",
        database_url="postgresql+asyncpg://u:p@db:5432/d",
        redis_url="redis://cache:6379/0",
        kafka_bootstrap_servers="kafka:9092",
    )  # type: ignore[call-arg]
    configure_logging(settings)
    try:
        client.get("/missing")
        line = capsys.readouterr().out.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["event"] == "request.error"
        assert parsed["level"] == "warning"
        assert parsed["code"] == "RESOURCE_NOT_FOUND"
        assert parsed["status"] == 404
        assert "/missing" in parsed["path"]
        assert parsed["detail"] == "Customer with id '7' was not found."
    finally:
        structlog.reset_defaults()
        structlog.contextvars.clear_contextvars()
