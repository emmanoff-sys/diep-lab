"""Integration tests for explain_device_state endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from copilot.helpers.explain_device_state import explain_device_state
from copilot.providers.base_provider import BaseProvider
from copilot.cache import RedisCache

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.helpers.health_helper.evaluate_health_for_device')
def test_tenant_isolation(
    mock_eval_health, mock_get_telemetry, mock_get_device
):
    """Test tenant isolation works correctly."""
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
    
    # Test with tenant
    result = explain_device_state("BAT001", tenant="acme")
    
    assert result["device_id"] == "BAT001"
    assert result["health_summary"]["health"] == "OK"
    
    # Verify tenant was passed to get_device_row
    mock_get_device.assert_called_with("BAT001", tenant="acme")

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.helpers.health_helper.evaluate_health_for_device')
def test_cache_integration(
    mock_eval_health, mock_get_telemetry, mock_get_device
):
    """Test cache integration works correctly."""
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
    
    # Test with cache
    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.get.return_value = None  # Cache miss
    
    result = explain_device_state("BAT001", cache=mock_cache)
    
    assert result["device_id"] == "BAT001"
    assert result["health_summary"]["health"] == "OK"

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.helpers.health_helper.evaluate_health_for_device')
def test_provider_failover(
    mock_eval_health, mock_get_telemetry, mock_get_device
):
    """Test provider failover works correctly."""
    # Setup mocks
    mock_get_device.return_value = {
        "device_id": "BAT001",
        "device_type": "battery",
        "status": "DEGRADED",
        "site_name": "Site A"
    }
    
    mock_get_telemetry.return_value = [{"time": "2026-01-01T00:00:00Z", "voltage": 200}]
    mock_eval_health.return_value = {
        "health": "DEGRADED",
        "reason": "Low voltage",
        "is_online": False,
        "has_critical_alarm": True,
        "telemetry_fresh": True
    }
    
    # Test with failing provider
    mock_provider = MagicMock(spec=BaseProvider)
    mock_provider.invoke.side_effect = Exception("Provider failed")
    
    result = explain_device_state("BAT001", provider=mock_provider)
    
    assert result["device_id"] == "BAT001"
    assert "error" in json.loads(result["explanation"])

@patch('copilot.helpers.db_queries.get_device_row')
@patch('copilot.helpers.db_queries.get_recent_telemetry')
@patch('copilot.helpers.health_helper.evaluate_health_for_device')
def test_missing_telemetry_handling(
    mock_eval_health, mock_get_telemetry, mock_get_device
):
    """Test handling of missing telemetry data."""
    # Setup mocks
    mock_get_device.return_value = {
        "device_id": "BAT001",
        "device_type": "battery",
        "status": "ONLINE",
        "site_name": "Site A"
    }
    
    mock_get_telemetry.return_value = []  # No telemetry
    mock_eval_health.return_value = {
        "health": "DEGRADED",
        "reason": "No telemetry data",
        "is_online": False,
        "has_critical_alarm": False,
        "telemetry_fresh": False
    }
    
    # Test
    result = explain_device_state("BAT001")
    
    assert result["device_id"] == "BAT001"
    assert result["health_summary"]["health"] == "DEGRADED"
    assert len(result["telemetry_data"]) == 0

@patch('copilot.helpers.db_queries.get_device_row')
def test_invalid_device_handling(mock_get_device):
    """Test handling of invalid device IDs."""
    mock_get_device.return_value = None
    
    result = explain_device_state("INVALID_DEVICE")
    
    assert result["error"] == "Device not found"
    assert result["health_summary"]["health"] == "UNKNOWN"

__all__ = [
    "test_tenant_isolation",
    "test_cache_integration",
    "test_provider_failover",
    "test_missing_telemetry_handling",
    "test_invalid_device_handling"
]