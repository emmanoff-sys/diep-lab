"""Abstract base class for LLM providers.

All providers must implement ``invoke(prompt: str) -> str`` which returns
the LLM's response text, or raises ``ProviderError`` on failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderError(Exception):
    """Raised when an LLM provider fails to produce a response.

    Attributes:
        message: Human-readable error description.
        provider_name: Name of the provider that failed.
        status_code: Optional HTTP status code from the provider API.
    """

    def __init__(
        self,
        message: str,
        provider_name: str = "unknown",
        status_code: int | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.status_code = status_code
        super().__init__(f"[{provider_name}] {message}")


class BaseProvider(ABC):
    """Abstract base class for all LLM providers.

    Subclasses must implement ``invoke()`` and provide a ``name`` attribute.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g., ``"openrouter"``, ``"ollama_local"``)."""
        ...

    @abstractmethod
    def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt to the LLM and return the response text.

        Args:
            prompt: The prompt string to send.
            **kwargs: Additional provider-specific parameters (e.g., temperature,
                max_tokens, model override).

        Returns:
            The LLM response text.

        Raises:
            ProviderError: If the provider is unavailable, times out, or
                returns an error response.
        """
        ...


__all__ = ["BaseProvider", "ProviderError"]