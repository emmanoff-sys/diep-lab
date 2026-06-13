"""Explain device state endpoint implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

from copilot.helpers.tenant_filter import apply_tenant_filter
from copilot.helpers.db_queries import get_device_row, get_recent_telemetry
from copilot.helpers.health_helper import evaluate_health_for_device
from copilot.cache import RedisCache
from copilot.providers.base_provider import BaseProvider

logger = logging.getLogger("diep-copilot.explain_device_state")

def explain_device_state(
    device_id: str,
    tenant: str | None = None,
    provider: BaseProvider | None = None,
    cache: RedisCache | None = None,
) -> dict[str, Any]:
    """Generate an explanation for a device's current state.
    
    Args:
        device_id: The device identifier.
        tenant: Optional tenant ID for isolation filtering.
        provider: LLM provider for generating explanations.
        cache: Redis cache instance for response caching.
    
    Returns:
        Dict containing:
            - device_id
            - health_summary
            - explanation
            - telemetry_data 
            - context
    """
    # Get device metadata from database
    device_row = get_device_row(device_id, tenant=tenant)
    if not device_row:
        return {
            "device_id": device_id,
            "error": "Device not found",
            "health_summary": {"health": "UNKNOWN", "reason": "Device not found"}
        }

    # Get recent telemetry (limit 5)
    telemetry = get_recent_telemetry(device_id, limit=5)
    
    # Generate health assessment
    health = evaluate_health_for_device(
        device_id=device_id,
        device_row=device_row,
        device_state=telemetry[0] if telemetry else None,
    )

    # Build context for LLM
    context = {
        "device_id": device_id,
        "device_type": device_row["device_type"],
        "status": device_row["status"],
        "site_name": device_row["site_name"],
        "telemetry": telemetry,
        "health": health,
    }

    # Generate explanation using provider
    explanation = ""
    if provider:
        try:
            prompt = build_prompt(context)
            explanation = provider.invoke(prompt)
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            explanation = json.dumps({
                "error": "Failed to generate explanation",
                "context": context
            })

    return {
        "device_id": device_id,
        "health_summary": health,
        "explanation": explanation,
        "telemetry_data": telemetry,
        "context": context
    }

def build_prompt(context: dict[str, Any]) -> str:
    """Build the prompt for the LLM provider."""
    return (
        f"Analyze the following device state and provide a concise explanation "
        f"of its current operational status. Device ID: {context['device_id']}, "
        f"Type: {context['device_type']}, Status: {context['status']}, "
        f"Site: {context['site_name']}, Health: {context['health']['health']}. "
        f"Recent telemetry: {json.dumps(context['telemetry'], indent=2)} "
        f"Explain any anomalies or concerns for an operations team."
    )

__all__ = ["explain_device_state", "build_prompt"]