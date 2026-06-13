"""Tests for explain_device_state helper."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from copilot.helpers.explain_device_state import explain_device_state, build_prompt
from copilot.providers.base_provider import BaseProvider
from copilot.cache import RedisCache

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.helpers.health_helper.evaluate_health_for_device')
def test_explain_device_state_no_provider(
    mock_eval_health, mock_get_telemetry, mock_get_device
):
    """Test basic functionality without an LLM provider."""
    # Setup mocks
    mock_get_device.return_value = {
        "device_id": "BAT001",
        "device_type": "battery",
        "status": "ONLINE",
        "site_name": "Site A"
    }
    
    mock_get_telemetry.return_value = [{"time": "2026-01-01T00:00:00Z", "voltage": 230}]
    mock_eval_health.return_value = {
        "health": "OK",
        "reason": "Normal operation",
        "is_online": True,
        "has_critical_alarm": False,
        "telemetry_fresh": True
    }
    
    # Test
    result = explain_device_state("BAT001")
    
    assert result["device_id"] == "BAT001"
    assert result["health_summary"]["health"] == "OK"
    assert len(result["telemetry_data"]) == 1
    assert "explanation" not in result  # No provider means no explanation

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
def test_explain_device_state_with_provider(
    mock_get_telemetry, mock_get_device,
):
    """Test with an LLM provider."""
    # Setup mocks
    mock_get_device.return_value = {
        "device_id": "BAT001",
        "device_type": "battery",
        "status": "DEGRADED",
        "site_name": "Site A"
    }
    
    mock_get_telemetry.return_value = [{"time": "2026-01-01T00:00:00Z", "voltage": 200}]
    
    mock_provider = MagicMock(spec=BaseProvider)
    mock_provider.invoke.return_value = json.dumps({"explanation": "Voltage low"})
    
    # Test
    result = explain_device_state("BAT001", provider=mock_provider)
    
    assert result["device_id"] == "BAT001"
    assert "explanation" in result
    assert json.loads(result["explanation"])["explanation"] == "Voltage low"
    mock_provider.invoke.assert_called_once()

def test_build_prompt():
    """Test prompt construction."""
    context = {
        "device_id": "BAT001",
        "device_type": "battery",
        "status": "DEGRADED",
        "site_name": "Site A",
        "health": {"health": "DEGRADED"},
        "telemetry": [{"voltage": 200}]
    }
    
    prompt = build_prompt(context)
    
    assert "BAT001" in prompt
    assert "battery" in prompt
    assert "DEGRADED" in prompt
    assert "Site A" in prompt
    assert "200" in prompt

@patch('copilot.helpers.db_queries.get_device_row')
def test_explain_device_state_not_found(mock_get_device):
    """Test handling of unknown device."""
    mock_get_device.return_value = None
    
    result = explain_device_state("UNKNOWN")
    
    assert result["error"] == "Device not found"
    assert result["health_summary"]["health"] == "UNKNOWN"

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.providers.base_provider.BaseProvider.invoke')
def test_provider_error_handling(
    mock_invoke, mock_get_telemetry, mock_get_device
):
    """Test graceful handling of provider errors."""
    mock_get_device.return_value = {"device_id": "BAT001"}
    mock_get_telemetry.return_value = []
    mock_invoke.side_effect = Exception("Provider failed")
    
    mock_provider = MagicMock(spec=BaseProvider)
    mock_provider.invoke = mock_invoke
    
    result = explain_device_state("BAT001", provider=mock_provider)
    
    assert "error" in json.loads(result["explanation"])

__all__ = [
    "test_explain_device_state_no_provider",
    "test_explain_device_state_with_provider",
    "test_build_prompt",
    "test_explain_device_state_not_found",
    "test_provider_error_handling"
]