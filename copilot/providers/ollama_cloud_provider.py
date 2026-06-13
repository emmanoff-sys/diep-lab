"""Ollama Cloud provider — tertiary LLM provider.

Connects to the Ollama Cloud API (``https://api.ollama.com/v1/chat/completions``).

Configuration is via environment variables:
- ``OLLAMA_CLOUD_API_KEY``: API key for Ollama Cloud (required).
- ``OLLAMA_CLOUD_MODEL``: Model name (default: ``qwen3:32b``).
- ``OLLAMA_CLOUD_URL``: API base URL (default: ``https://api.ollama.com/v1/chat/completions``).
- ``OLLAMA_CLOUD_TIMEOUT``: Request timeout in seconds (default: 10).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from copilot.providers.base_provider import BaseProvider, ProviderError

logger = logging.getLogger("diep-copilot.ollama_cloud")

OLLAMA_CLOUD_API_KEY = os.getenv("OLLAMA_CLOUD_API_KEY", "")
OLLAMA_CLOUD_MODEL = os.getenv("OLLAMA_CLOUD_MODEL", "qwen3:32b")
OLLAMA_CLOUD_URL = os.getenv(
    "OLLAMA_CLOUD_URL",
    "https://api.ollama.com/v1/chat/completions",
)
OLLAMA_CLOUD_TIMEOUT = int(os.getenv("OLLAMA_CLOUD_TIMEOUT", "10"))


class OllamaCloudProvider(BaseProvider):
    """LLM provider that calls the Ollama Cloud API.

    Args:
        api_key: Ollama Cloud API key. Defaults to ``OLLAMA_CLOUD_API_KEY`` env var.
        model: Model name. Defaults to ``qwen3:32b``.
        base_url: API endpoint URL.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self._api_key = api_key or OLLAMA_CLOUD_API_KEY
        self._model = model or OLLAMA_CLOUD_MODEL
        self._base_url = base_url or OLLAMA_CLOUD_URL
        self._timeout = timeout or OLLAMA_CLOUD_TIMEOUT

        if not self._api_key:
            logger.warning(
                "OLLAMA_CLOUD_API_KEY is not set — provider will fail at runtime"
            )

    @property
    def name(self) -> str:
        return "ollama_cloud"

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to Ollama Cloud and return the response.

        Args:
            prompt: The prompt string.
            **kwargs: Overrides for model, temperature, max_tokens, etc.

        Returns:
            Response text from the LLM.

        Raises:
            ProviderError: On connection failure, timeout, or API error.
        """
        if not self._api_key:
            raise ProviderError(
                "OLLAMA_CLOUD_API_KEY is not configured",
                provider_name=self.name,
            )

        model = kwargs.get("model", self._model)
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2048)

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    self._base_url,
                    json=payload,
                    headers=headers,
                )

            if response.status_code == 401:
                raise ProviderError(
                    "Invalid Ollama Cloud API key (401)",
                    provider_name=self.name,
                    status_code=401,
                )
            if response.status_code == 429:
                raise ProviderError(
                    "Ollama Cloud rate limit exceeded (429)",
                    provider_name=self.name,
                    status_code=429,
                )
            if response.status_code >= 500:
                raise ProviderError(
                    f"Ollama Cloud server error ({response.status_code})",
                    provider_name=self.name,
                    status_code=response.status_code,
                )
            if response.status_code != 200:
                raise ProviderError(
                    f"Ollama Cloud returned {response.status_code}: {response.text[:200]}",
                    provider_name=self.name,
                    status_code=response.status_code,
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise ProviderError(
                    "Ollama Cloud returned empty choices",
                    provider_name=self.name,
                )

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ProviderError(
                    "Ollama Cloud returned empty content",
                    provider_name=self.name,
                )
            return content

        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Ollama Cloud request timed out after {self._timeout}s",
                provider_name=self.name,
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to Ollama Cloud at {self._base_url}",
                provider_name=self.name,
            ) from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Invalid JSON response from Ollama Cloud",
                provider_name=self.name,
            ) from exc


__all__ = ["OllamaCloudProvider"]