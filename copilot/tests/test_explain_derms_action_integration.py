"""Integration tests for explain_derms_action endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from copilot.helpers.explain_derms_action import explain_derms_action
from copilot.providers.base_provider import BaseProvider
from copilot.cache import RedisCache

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
def test_tenant_isolation(mock_get_device, mock_get_derms):
    """Test tenant isolation works correctly."""
    # Setup mocks
    mock_get_derms.return_value = {
        "request_id": "a1b2c3d4",
        "device_id": "BAT001",
        "site_name": "Site A"
    }
    mock_get_device.return_value = {"device_id": "BAT001"}
    
    # Test with tenant
    result = explain_derms_action("a1b2c3d4", tenant="acme")
    
    assert result["action_id"] == "a1b2c3d4"
    
    # Verify tenant was passed to get_derms_request
    mock_get_derms.assert_called_with("a1b2c3d4", tenant="acme")
    mock_get_device.assert_called_with("BAT001", tenant="acme")

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
def test_cache_integration(mock_get_device, mock_get_derms):
    """Test cache integration works correctly."""
    # Setup mocks
    mock_get_derms.return_value = {"device_id": "BAT001"}
    mock_get_device.return_value = {"device_id": "BAT001"}
    
    # Test with cache
    mock_cache = MagicMock(spec=RedisCache)
    mock_cache.get.return_value = None  # Cache miss
    
    result = explain_derms_action("a1b2c3d4", cache=mock_cache)
    
    assert result["action_id"] == "a1b2c3d4"

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
def test_provider_failover(mock_get_device, mock_get_derms):
    """Test provider failover works correctly."""
    # Setup mocks
    mock_get_derms.return_value = {"device_id": "BAT001"}
    mock_get_device.return_value = {"device_id": "BAT001"}
    
    # Test with failing provider
    mock_provider = MagicMock(spec=BaseProvider)
    mock_provider.invoke.side_effect = Exception("Provider failed")
    
    result = explain_derms_action("a1b2c3d4", provider=mock_provider)
    
    assert "error" in json.loads(result["explanation"])

@patch('copilot.helpers.db_queries.get_derms_request')
@patch('copilot.helpers.db_queries.get_device_row')
def test_empty_telemetry_handling(mock_get_device, mock_get_derms):
    """Test handling of empty telemetry data."""
    # Setup mocks
    mock_get_derms.return_value = {"device_id": "BAT001"}
    mock_get_device.return_value = {"device_id": "BAT001"}
    
    # Test
    result = explain_derms_action("a1b2c3d4")
    
    assert result["action_id"] == "a1b2c3d4"

__all__ = [
    "test_tenant_isolation",
    "test_cache_integration",
    "test_provider_failover",
    "test_empty_telemetry_handling"
]