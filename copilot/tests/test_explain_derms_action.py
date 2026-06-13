"""Tests for explain_derms_action helper."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from copilot.helpers.explain_derms_action import explain_derms_action, build_prompt
from copilot.providers.base_provider import BaseProvider
from copilot.cache import RedisCache

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.helpers.db_queries.get_alarms_by_device')
@patch('copilot.helpers.db_queries.get_device_certifications')
@patch('copilot.helpers.health_helper.evaluate_health_for_device')
def test_explain_derms_action_no_provider(
    mock_eval_health, mock_get_certs, mock_get_alarms, 
    mock_get_telemetry, mock_get_device, mock_get_derms
):
    """Test basic functionality without an LLM provider."""
    # Setup mocks
    mock_get_derms.return_value = {
        "request_id": "a1b2c3d4",
        "request_type": "battery_dispatch",
        "device_id": "BAT001",
        "site_name": "Site A",
        "params": {"target_soc": 80},
        "status": "COMPLETED",
        "created_at": "2026-01-01T00:00:00Z",
        "executed_at": "2026-01-01T00:05:00Z",
        "completed_at": "2026-01-01T00:30:00Z"
    }
    
    mock_get_device.return_value = {
        "device_id": "BAT001",
        "device_type": "battery",
        "status": "ONLINE"
    }
    
    mock_get_telemetry.return_value = [{"time": "2026-01-01T00:00:00Z", "voltage": 230}]
    mock_get_alarms.return_value = []
    mock_get_certs.return_value = [{"test_name": "safety", "result": "PASS"}]
    mock_eval_health.return_value = {"health": "OK"}
    
    # Test
    result = explain_derms_action("a1b2c3d4")
    
    assert result["action_id"] == "a1b2c3d4"
    assert result["action_summary"]["type"] == "battery_dispatch"
    assert "explanation" not in result  # No provider means no explanation

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
def test_explain_derms_action_not_found(mock_get_device, mock_get_derms):
    """Test handling of unknown action."""
    mock_get_derms.return_value = None
    
    result = explain_derms_action("UNKNOWN")
    
    assert result["error"] == "Action not found"
    assert result["action_summary"] is None

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.providers.base_provider.BaseProvider.invoke')
def test_provider_error_handling(
    mock_invoke, mock_get_device, mock_get_derms
):
    """Test graceful handling of provider errors."""
    mock_get_derms.return_value = {"device_id": "BAT001"}
    mock_get_device.return_value = {"device_id": "BAT001"}
    mock_invoke.side_effect = Exception("Provider failed")
    
    mock_provider = MagicMock(spec=BaseProvider)
    mock_provider.invoke = mock_invoke
    
    result = explain_derms_action("a1b2c3d4", provider=mock_provider)
    
    assert "error" in json.loads(result["explanation"])

def test_build_prompt():
    """Test prompt construction."""
    context = {
        "action_id": "a1b2c3d4",
        "action_type": "battery_dispatch",
        "action_status": "COMPLETED",
        "device_id": "BAT001",
        "site_name": "Site A",
        "action_params": {"target_soc": 80},
        "health_status": {"health": "OK"},
        "telemetry": [{"voltage": 230}],
        "alarms": []
    }
    
    prompt = build_prompt(context)
    
    assert "a1b2c3d4" in prompt
    assert "battery_dispatch" in prompt
    assert "BAT001" in prompt
    assert "Site A" in prompt
    assert "80" in prompt

__all__ = [
    "test_explain_derms_action_no_provider",
    "test_explain_derms_action_not_found",
    "test_provider_error_handling",
    "test_build_prompt"
]