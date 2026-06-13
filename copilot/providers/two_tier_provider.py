"""Three-tier LLM provider with fallback chain.

Implements the provider priority:
  1. Primary: OpenRouter (DeepSeek V3)
  2. Secondary: Local Ollama (qwen3:4b)
  3. Tertiary: Ollama Cloud

When all three tiers fail, a static fallback response is returned with the
original context, allowing the endpoint to still respond with raw data even
when the LLM is completely unavailable.

The provider exposes Prometheus metrics for:
- ``copilot_provider_errors_total``: Counter per provider + error type.
- ``copilot_provider_latency_seconds``: Histogram per provider.
- ``copilot_fallback_activated_total``: Counter for fallback activations.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from prometheus_client import Counter, Histogram

from copilot.providers.base_provider import BaseProvider, ProviderError

logger = logging.getLogger("diep-copilot.three_tier")

# Prometheus metrics
provider_errors = Counter(
    "copilot_provider_errors_total",
    "LLM provider errors",
    ["provider", "error_type"],
)

provider_latency = Histogram(
    "copilot_provider_latency_seconds",
    "LLM invocation latency",
    ["provider"],
    buckets=(0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, float("inf")),
)

fallback_activated = Counter(
    "copilot_fallback_activated_total",
    "Number of fallback activations",
    ["primary_provider"],
)


class ThreeTierProvider(BaseProvider):
    """Provider that tries primary, then secondary, then tertiary, then static fallback.

    Args:
        primary: The primary LLM provider (OpenRouter DeepSeek V3).
        secondary: The secondary provider (local Ollama qwen3:4b).
        tertiary: The tertiary provider (Ollama Cloud).
        static_fallback_prompt: If provided, used to generate the static fallback
            response when all providers are unavailable.
    """

    def __init__(
        self,
        primary: BaseProvider,
        secondary: BaseProvider,
        tertiary: BaseProvider,
        static_fallback_prompt: str | None = None,
    ) -> None:
        self._primary = primary
        self._secondary = secondary
        self._tertiary = tertiary
        self._static_fallback_prompt = static_fallback_prompt

    @property
    def name(self) -> str:
        return f"three_tier({self._primary.name} > {self._secondary.name} > {self._tertiary.name})"

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Invoke the three-tier chain.

        Tiers are tried in order. If all fail, returns a static fallback JSON
        string (not a ProviderError) so the endpoint can respond gracefully.

        Args:
            prompt: The prompt string.
            **kwargs: Additional parameters forwarded to each provider.

        Returns:
            Response text from the first successful provider, or a static
            fallback JSON string if all providers fail.
        """
        tiers = [
            ("primary", self._primary),
            ("secondary", self._secondary),
            ("tertiary", self._tertiary),
        ]

        last_error: ProviderError | None = None

        for tier_name, provider in tiers:
            try:
                start = time.monotonic()
                result = provider.invoke(prompt, **kwargs)
                elapsed = time.monotonic() - start

                # Record metrics
                provider_latency.labels(provider=provider.name).observe(elapsed)

                logger.info(
                    "LLM provider '%s' succeeded in %.2fs (tier: %s)",
                    provider.name,
                    elapsed,
                    tier_name,
                )

                # If we used a fallback, record it
                if tier_name != "primary":
                    fallback_activated.labels(
                        primary_provider=self._primary.name
                    ).inc()

                return result

            except ProviderError as exc:
                elapsed = time.monotonic() - start if 'start' in dir() else 0
                last_error = exc

                error_type = _classify_error(exc)
                provider_errors.labels(
                    provider=provider.name,
                    error_type=error_type,
                ).inc()

                logger.warning(
                    "LLM provider '%s' failed (tier: %s, error_type: %s): %s",
                    provider.name,
                    tier_name,
                    error_type,
                    exc,
                )

                # If it's an auth error, don't try other tiers (they'll also fail)
                if error_type == "auth":
                    logger.critical(
                        "Authentication error on '%s' — not trying fallbacks",
                        provider.name,
                    )
                    break

        # All tiers failed — return static fallback
        logger.critical(
            "All LLM providers unavailable. Last error: %s", last_error
        )

        return self._build_static_fallback(prompt)

    def _build_static_fallback(self, prompt: str) -> str:
        """Build a static fallback response when no LLM is available.

        The response includes the original context so the operator can still
        see the raw data.

        Args:
            prompt: The original assembled prompt (contains all context data).

        Returns:
            JSON string with the fallback response.
        """
        # Extract a summary from the prompt for the fallback message.
        # The prompt is structured text — we include it as context_data.
        fallback = {
            "answer": (
                "LLM provider is temporarily unavailable. The request context "
                "has been assembled but could not be processed by the language model. "
                "Raw context data is included below for manual review."
            ),
            "data_sources": ["static_fallback"],
            "confidence": 0.0,
            "fallback": True,
            "context_data": prompt,
        }
        return json.dumps(fallback)


def _classify_error(error: ProviderError) -> str:
    """Classify a ProviderError into a Prometheus-friendly error type label.

    Args:
        error: The provider error.

    Returns:
        One of "auth", "timeout", "rate_limit", "server_error", "connectivity",
        "model_not_found", or "unknown".
    """
    msg = str(error).lower()
    code = error.status_code

    if code == 401 or code == 403:
        return "auth"
    if code == 429 or "rate limit" in msg:
        return "rate_limit"
    if "timeout" in msg:
        return "timeout"
    if code and 500 <= code < 600:
        return "server_error"
    if "connect" in msg or "connection" in msg:
        return "connectivity"
    if code == 404 or "not found" in msg:
        return "model_not_found"
    return "unknown"


__all__ = ["ThreeTierProvider"]