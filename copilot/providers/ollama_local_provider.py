"""Local Ollama provider — secondary LLM provider using qwen3:4b.

Connects to a locally running Ollama daemon (default: ``http://localhost:11434/api/chat``).

Configuration is via environment variables:
- ``OLLAMA_LOCAL_URL``: Ollama API base URL (default: ``http://localhost:11434/api/chat``).
- ``OLLAMA_LOCAL_MODEL``: Model name (default: ``qwen3:4b``).
- ``OLLAMA_LOCAL_TIMEOUT``: Request timeout in seconds (default: 10).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from copilot.providers.base_provider import BaseProvider, ProviderError

logger = logging.getLogger("diep-copilot.ollama_local")

OLLAMA_LOCAL_URL = os.getenv("OLLAMA_LOCAL_URL", "http://localhost:11434/api/chat")
OLLAMA_LOCAL_MODEL = os.getenv("OLLAMA_LOCAL_MODEL", "qwen3:4b")
OLLAMA_LOCAL_TIMEOUT = int(os.getenv("OLLAMA_LOCAL_TIMEOUT", "10"))


class OllamaLocalProvider(BaseProvider):
    """LLM provider that calls a local Ollama daemon.

    Args:
        base_url: Ollama API URL. Defaults to ``OLLAMA_LOCAL_URL`` env var.
        model: Model name. Defaults to ``qwen3:4b``.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self._base_url = base_url or OLLAMA_LOCAL_URL
        self._model = model or OLLAMA_LOCAL_MODEL
        self._timeout = timeout or OLLAMA_LOCAL_TIMEOUT

    @property
    def name(self) -> str:
        return "ollama_local"

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to local Ollama and return the response.

        Args:
            prompt: The prompt string.
            **kwargs: Overrides for model, temperature, etc.

        Returns:
            Response text from the LLM.

        Raises:
            ProviderError: On connection failure, timeout, or API error.
        """
        model = kwargs.get("model", self._model)
        temperature = kwargs.get("temperature", 0.7)

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {
                "temperature": temperature,
            },
            "stream": False,
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(self._base_url, json=payload)

            if response.status_code == 404:
                raise ProviderError(
                    f"Model '{model}' not found locally. Run: ollama pull {model}",
                    provider_name=self.name,
                    status_code=404,
                )
            if response.status_code >= 500:
                raise ProviderError(
                    f"Local Ollama server error ({response.status_code})",
                    provider_name=self.name,
                    status_code=response.status_code,
                )
            if response.status_code != 200:
                raise ProviderError(
                    f"Local Ollama returned {response.status_code}: {response.text[:200]}",
                    provider_name=self.name,
                    status_code=response.status_code,
                )

            data = response.json()
            message = data.get("message", {})
            content = message.get("content", "")
            if not content:
                raise ProviderError(
                    "Local Ollama returned empty content",
                    provider_name=self.name,
                )
            return content

        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Local Ollama request timed out after {self._timeout}s",
                provider_name=self.name,
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to local Ollama at {self._base_url}. "
                f"Is the Ollama daemon running?",
                provider_name=self.name,
            ) from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Invalid JSON response from local Ollama",
                provider_name=self.name,
            ) from exc


__all__ = ["OllamaLocalProvider"]