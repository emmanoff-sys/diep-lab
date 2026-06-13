"""Unit tests for LLM provider abstraction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from copilot.providers.base_provider import BaseProvider, ProviderError
from copilot.providers.openrouter_provider import OpenRouterProvider
from copilot.providers.ollama_local_provider import OllamaLocalProvider
from copilot.providers.ollama_cloud_provider import OllamaCloudProvider
from copilot.providers.two_tier_provider import ThreeTierProvider, _classify_error


class TestBaseProvider:
    """Tests for BaseProvider contract."""

    def test_provider_error_message(self) -> None:
        error = ProviderError("Something went wrong", provider_name="test_provider")
        assert "test_provider" in str(error)
        assert "Something went wrong" in str(error)

    def test_provider_error_with_status_code(self) -> None:
        error = ProviderError("Not found", provider_name="test", status_code=404)
        assert error.status_code == 404

    def test_cannot_instantiate_base_class(self) -> None:
        with pytest.raises(TypeError):
            BaseProvider()  # type: ignore[abstract]


class MockSuccessProvider(BaseProvider):
    """A mock provider that always succeeds."""

    def __init__(self, response: str = "Mock response") -> None:
        self._response = response

    @property
    def name(self) -> str:
        return "mock_success"

    def invoke(self, prompt: str, **kwargs) -> str:
        return self._response


class MockFailProvider(BaseProvider):
    """A mock provider that always raises ProviderError."""

    def __init__(self, error_message: str = "Mock failure") -> None:
        self._error_message = error_message

    @property
    def name(self) -> str:
        return "mock_fail"

    def invoke(self, prompt: str, **kwargs) -> str:
        raise ProviderError(self._error_message, provider_name=self.name)


class MockAuthFailProvider(BaseProvider):
    """A mock provider that raises auth error."""

    @property
    def name(self) -> str:
        return "mock_auth_fail"

    def invoke(self, prompt: str, **kwargs) -> str:
        raise ProviderError("Invalid API key", provider_name=self.name, status_code=401)


class TestThreeTierProvider:
    """Tests for ThreeTierProvider fallback chain."""

    def test_primary_succeeds(self) -> None:
        primary = MockSuccessProvider("Primary answer")
        secondary = MockFailProvider()
        tertiary = MockFailProvider()
        provider = ThreeTierProvider(primary, secondary, tertiary)
        result = provider.invoke("test prompt")
        assert result == "Primary answer"

    def test_fallback_to_secondary(self) -> None:
        primary = MockFailProvider("Primary failed")
        secondary = MockSuccessProvider("Secondary answer")
        tertiary = MockFailProvider()
        provider = ThreeTierProvider(primary, secondary, tertiary)
        result = provider.invoke("test prompt")
        assert result == "Secondary answer"

    def test_fallback_to_tertiary(self) -> None:
        primary = MockFailProvider("Primary failed")
        secondary = MockFailProvider("Secondary failed")
        tertiary = MockSuccessProvider("Tertiary answer")
        provider = ThreeTierProvider(primary, secondary, tertiary)
        result = provider.invoke("test prompt")
        assert result == "Tertiary answer"

    def test_all_fail_returns_static_fallback(self) -> None:
        primary = MockFailProvider("Primary failed")
        secondary = MockFailProvider("Secondary failed")
        tertiary = MockFailProvider("Tertiary failed")
        provider = ThreeTierProvider(primary, secondary, tertiary)
        result = provider.invoke("test prompt")
        # Should return a JSON string with fallback=True
        parsed = json.loads(result)
        assert parsed["fallback"] is True
        assert parsed["confidence"] == 0.0
        assert "context_data" in parsed

    def test_auth_error_does_not_try_fallbacks(self) -> None:
        primary = MockAuthFailProvider()
        secondary = MockSuccessProvider("Should not be reached")
        tertiary = MockSuccessProvider("Should not be reached")
        provider = ThreeTierProvider(primary, secondary, tertiary)
        result = provider.invoke("test prompt")
        # Auth error → should stop and return static fallback
        parsed = json.loads(result)
        assert parsed["fallback"] is True

    def test_static_fallback_includes_context(self) -> None:
        primary = MockFailProvider()
        secondary = MockFailProvider()
        tertiary = MockFailProvider()
        provider = ThreeTierProvider(primary, secondary, tertiary)
        result = provider.invoke("This is my context data for the LLM")
        parsed = json.loads(result)
        assert "context_data" in parsed
        assert "This is my context data" in parsed["context_data"]

    @property
    def name(self) -> str:
        return "three_tier_test"


class TestClassifyError:
    """Tests for _classify_error utility."""

    def test_auth_error(self) -> None:
        error = ProviderError("Unauthorized", status_code=401)
        assert _classify_error(error) == "auth"

    def test_forbidden_error(self) -> None:
        error = ProviderError("Forbidden", status_code=403)
        assert _classify_error(error) == "auth"

    def test_rate_limit_error(self) -> None:
        error = ProviderError("Rate limit exceeded", status_code=429)
        assert _classify_error(error) == "rate_limit"

    def test_rate_limit_in_message(self) -> None:
        error = ProviderError("rate limit hit", status_code=200)
        assert _classify_error(error) == "rate_limit"

    def test_timeout_error(self) -> None:
        error = ProviderError("Request timed out")
        assert _classify_error(error) == "timeout"

    def test_server_error(self) -> None:
        error = ProviderError("Server error", status_code=500)
        assert _classify_error(error) == "server_error"

    def test_server_error_502(self) -> None:
        error = ProviderError("Bad gateway", status_code=502)
        assert _classify_error(error) == "server_error"

    def test_connectivity_error(self) -> None:
        error = ProviderError("Cannot connect to host")
        assert _classify_error(error) == "connectivity"

    def test_connection_in_message(self) -> None:
        error = ProviderError("Connection refused")
        assert _classify_error(error) == "connectivity"

    def test_model_not_found(self) -> None:
        error = ProviderError("Model not found", status_code=404)
        assert _classify_error(error) == "model_not_found"

    def test_not_found_in_message(self) -> None:
        error = ProviderError("not found: qwen3:4b")
        assert _classify_error(error) == "model_not_found"

    def test_unknown_error(self) -> None:
        error = ProviderError("Something weird happened")
        assert _classify_error(error) == "unknown"


class TestOpenRouterProvider:
    """Tests for OpenRouterProvider."""

    def test_no_api_key_raises_error(self) -> None:
        provider = OpenRouterProvider(api_key="")
        with pytest.raises(ProviderError, match="not configured"):
            provider.invoke("test")

    def test_provider_name(self) -> None:
        provider = OpenRouterProvider(api_key="sk-test")
        assert provider.name == "openrouter"

    @patch("httpx.Client.post")
    def test_successful_response(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter response"}}]
        }
        mock_post.return_value = mock_response

        provider = OpenRouterProvider(api_key="sk-test")
        result = provider.invoke("Hello")
        assert result == "OpenRouter response"

    @patch("httpx.Client.post")
    def test_server_error_raises(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_post.return_value = mock_response

        provider = OpenRouterProvider(api_key="sk-test")
        with pytest.raises(ProviderError, match="503"):
            provider.invoke("Hello")


class TestOllamaLocalProvider:
    """Tests for OllamaLocalProvider."""

    def test_provider_name(self) -> None:
        provider = OllamaLocalProvider()
        assert provider.name == "ollama_local"

    @patch("httpx.Client.post")
    def test_successful_response(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Local Ollama response"}
        }
        mock_post.return_value = mock_response

        provider = OllamaLocalProvider()
        result = provider.invoke("Hello")
        assert result == "Local Ollama response"

    @patch("httpx.Client.post")
    def test_model_not_found_raises(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response

        provider = OllamaLocalProvider()
        with pytest.raises(ProviderError, match="not found"):
            provider.invoke("Hello")


class TestOllamaCloudProvider:
    """Tests for OllamaCloudProvider."""

    def test_no_api_key_raises_error(self) -> None:
        provider = OllamaCloudProvider(api_key="")
        with pytest.raises(ProviderError, match="not configured"):
            provider.invoke("test")

    def test_provider_name(self) -> None:
        provider = OllamaCloudProvider(api_key="sk-test")
        assert provider.name == "ollama_cloud"

    @patch("httpx.Client.post")
    def test_successful_response(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Cloud response"}}]
        }
        mock_post.return_value = mock_response

        provider = OllamaCloudProvider(api_key="sk-test")
        result = provider.invoke("Hello")
        assert result == "Cloud response"