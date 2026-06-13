"""Explain DERMS action endpoint implementation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from copilot.helpers.tenant_filter import apply_tenant_filter
from copilot.helpers.db_queries import (
    get_derms_request,
    get_derms_actions_by_device_and_time,
    get_device_row,
    get_recent_telemetry,
    get_alarms_by_device,
    get_device_certifications
)
from copilot.helpers.health_helper import evaluate_health_for_device
from copilot.cache import RedisCache
from copilot.providers.base_provider import BaseProvider

logger = logging.getLogger("diep-copilot.explain_derms_action")

def explain_derms_action(
    action_id: str,
    tenant: str | None = None,
    provider: BaseProvider | None = None,
    cache: RedisCache | None = None,
) -> dict[str, Any]:
    """Generate an explanation for a DERMS action.
    
    Args:
        action_id: The DERMS action identifier (UUID).
        tenant: Optional tenant ID for isolation filtering.
        provider: LLM provider for generating explanations.
        cache: Redis cache instance for response caching.
    
    Returns:
        Dict containing:
            - action_id
            - action_summary
            - explanation
            - device_context
            - telemetry_data
            - alarm_history
            - certification_data
    """
    # Get DERMS action details
    action = get_derms_request(action_id, tenant=tenant)
    if not action:
        return {
            "action_id": action_id,
            "error": "Action not found",
            "action_summary": None
        }

    # Get device context
    device_row = get_device_row(action["device_id"], tenant=tenant)
    
    # Get telemetry from ±30 minutes around action time
    window_start = action["created_at"] - timedelta(minutes=30)
    window_end = action["created_at"] + timedelta(minutes=30)
    telemetry = get_recent_telemetry(action["device_id"], limit=100)
    
    # Get alarms from ±30 minutes around action time
    alarms = get_alarms_by_device(action["device_id"], limit=50, tenant=tenant)
    
    # Get device certifications
    certifications = get_device_certifications(action["device_id"])
    
    # Generate health assessment
    health = evaluate_health_for_device(
        device_id=action["device_id"],
        device_row=device_row,
        device_state=telemetry[0] if telemetry else None,
        recent_alarms=alarms
    )

    # Build context for LLM
    context = {
        "action_id": action_id,
        "action_type": action["request_type"],
        "action_params": action["params"],
        "action_status": action["status"],
        "device_id": action["device_id"],
        "device_type": device_row["device_type"] if device_row else None,
        "site_name": action["site_name"],
        "health_status": health,
        "telemetry": telemetry,
        "alarms": alarms,
        "certifications": certifications,
        "action_timestamp": action["created_at"]
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
        "action_id": action_id,
        "action_summary": {
            "type": action["request_type"],
            "params": action["params"],
            "status": action["status"],
            "created_at": action["created_at"],
            "executed_at": action["executed_at"],
            "completed_at": action["completed_at"]
        },
        "explanation": explanation,
        "device_context": {
            "device_id": action["device_id"],
            "device_type": device_row["device_type"] if device_row else None,
            "health_status": health,
            "site_name": action["site_name"]
        },
        "telemetry_data": telemetry,
        "alarm_history": alarms,
        "certification_data": certifications
    }

def build_prompt(context: dict[str, Any]) -> str:
    """Build the prompt for the LLM provider."""
    return (
        f"Analyze the following DERMS action and provide a concise explanation "
        f"of why it was executed and its outcome. Action ID: {context['action_id']}, "
        f"Type: {context['action_type']}, Status: {context['action_status']}, "
        f"Device: {context['device_id']}, Site: {context['site_name']}. "
        f"Action parameters: {json.dumps(context['action_params'])} "
        f"Device health at time of action: {context['health_status']['health']} "
        f"Recent telemetry: {json.dumps(context['telemetry'], indent=2)} "
        f"Recent alarms: {json.dumps(context['alarms'], indent=2)} "
        f"Explain the action's purpose and effectiveness for an operations team."
    )

__all__ = ["explain_derms_action", "build_prompt"]