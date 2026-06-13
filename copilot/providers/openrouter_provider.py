"""OpenRouter provider — primary LLM provider using DeepSeek V3.

Connects to the OpenRouter API (``https://openrouter.ai/api/v1/chat/completions``)
using the DeepSeek V3 model (``deepseek/deepseek-chat``).

Configuration is via environment variables:
- ``OPENROUTER_API_KEY``: API key for OpenRouter (required).
- ``OPENROUTER_MODEL``: Model identifier (default: ``deepseek/deepseek-chat``).
- ``OPENROUTER_URL``: Base URL (default: ``https://openrouter.ai/api/v1/chat/completions``).
- ``OPENROUTER_TIMEOUT``: Request timeout in seconds (default: 10).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from copilot.providers.base_provider import BaseProvider, ProviderError

logger = logging.getLogger("diep-copilot.openrouter")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
OPENROUTER_URL = os.getenv(
    "OPENROUTER_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)
OPENROUTER_TIMEOUT = int(os.getenv("OPENROUTER_TIMEOUT", "10"))


class OpenRouterProvider(BaseProvider):
    """LLM provider that calls OpenRouter API (DeepSeek V3).

    Args:
        api_key: OpenRouter API key. Defaults to ``OPENROUTER_API_KEY`` env var.
        model: Model identifier. Defaults to ``deepseek/deepseek-chat``.
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
        self._api_key = api_key or OPENROUTER_API_KEY
        self._model = model or OPENROUTER_MODEL
        self._base_url = base_url or OPENROUTER_URL
        self._timeout = timeout or OPENROUTER_TIMEOUT

        if not self._api_key:
            logger.warning(
                "OPENROUTER_API_KEY is not set — provider will fail at runtime"
            )

    @property
    def name(self) -> str:
        return "openrouter"

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to OpenRouter DeepSeek V3 and return the response.

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
                "OPENROUTER_API_KEY is not configured",
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
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://diep-energy.com",  # OpenRouter requires Referer
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
                    "Invalid OpenRouter API key (401)",
                    provider_name=self.name,
                    status_code=401,
                )
            if response.status_code == 429:
                raise ProviderError(
                    "OpenRouter rate limit exceeded (429)",
                    provider_name=self.name,
                    status_code=429,
                )
            if response.status_code >= 500:
                raise ProviderError(
                    f"OpenRouter server error ({response.status_code})",
                    provider_name=self.name,
                    status_code=response.status_code,
                )
            if response.status_code != 200:
                raise ProviderError(
                    f"OpenRouter returned {response.status_code}: {response.text[:200]}",
                    provider_name=self.name,
                    status_code=response.status_code,
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise ProviderError(
                    "OpenRouter returned empty choices",
                    provider_name=self.name,
                )

            content = choices[0].get("message", {}).get("content", "")
            return content

        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"OpenRouter request timed out after {self._timeout}s",
                provider_name=self.name,
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to OpenRouter at {self._base_url}",
                provider_name=self.name,
            ) from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Invalid JSON response from OpenRouter",
                provider_name=self.name,
            ) from exc


__all__ = ["OpenRouterProvider"]