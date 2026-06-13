"""LLM provider abstraction for the Copilot service.

Provides a three-tier provider chain:
  1. Primary: OpenRouter (DeepSeek V3)
  2. Secondary: Local Ollama (qwen3:4b)
  3. Tertiary: Ollama Cloud
  4. Static fallback when all tiers are unreachable

Usage:
    from copilot.providers.two_tier_provider import ThreeTierProvider
    from copilot.providers.openrouter_provider import OpenRouterProvider
    from copilot.providers.ollama_local_provider import OllamaLocalProvider
    from copilot.providers.ollama_cloud_provider import OllamaCloudProvider

    provider = ThreeTierProvider(
        primary=OpenRouterProvider(),
        secondary=OllamaLocalProvider(),
        tertiary=OllamaCloudProvider(),
    )
    answer = provider.invoke("Explain this alarm...")
"""

from __future__ import annotations

from .base_provider import BaseProvider
from .openrouter_provider import OpenRouterProvider
from .ollama_local_provider import OllamaLocalProvider
from .ollama_cloud_provider import OllamaCloudProvider
from .two_tier_provider import ThreeTierProvider

__all__ = [
    "BaseProvider",
    "OpenRouterProvider",
    "OllamaLocalProvider",
    "OllamaCloudProvider",
    "ThreeTierProvider",
]