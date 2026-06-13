"""Unit tests for ``db_queries`` parameterised SQL functions.

Uses mock database connections with ``MagicMock`` to verify query structure
and parameter passing without connecting to a real database.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from copilot.helpers.db_queries import (
    get_alarm_by_id,
    get_alarms_by_device,
    get_alarms_by_site,
    get_critical_alarms_count,
    get_24h_alarm_trend,
    get_device_row,
    get_fleet_counts,
    get_devices_by_site,
    get_recent_telemetry,
    get_derms_request,
    get_derms_actions_by_device_and_time,
    get_active_derms_by_site,
    get_last_command,
    get_command_by_device_and_time,
    get_device_onboarding,
    get_device_certifications,
    get_site_row,
    get_total_offline_count,
    get_offline_trend,
)


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create a mock psycopg2 connection."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    # Default: no rows returned
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    return conn


class TestGetAlarmById:
    """Tests for get_alarm_by_id."""

    def test_returns_alarm_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            42, "BAT001", "over_voltage", "HIGH",
            "Voltage exceeded 260V", {"threshold": 260},
            "2026-06-08T14:30:00Z",
        )
        result = get_alarm_by_id(mock_conn, 42)
        assert result is not None
        assert result["id"] == 42
        assert result["device_id"] == "BAT001"
        assert result["alarm_type"] == "over_voltage"
        assert result["severity"] == "HIGH"

    def test_returns_none_when_not_found(self, mock_conn) -> None:
        result = get_alarm_by_id(mock_conn, 999)
        assert result is None

    def test_tenant_filter_applied(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            42, "BAT001", "over_voltage", "HIGH",
            "Message", {}, "2026-06-08T14:30:00Z",
        )
        result = get_alarm_by_id(mock_conn, 42, tenant="acme")
        assert result is not None
        # Verify execute was called with tenant param
        execute_args = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args
        params = execute_args[0][1]
        assert "acme" in params


class TestGetDeviceRow:
    """Tests for get_device_row."""

    def test_returns_device_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1, "BAT001", "battery", "Abuja Site A", "ONLINE",
            "Abuja Site A", "acme", "2026-01-01T00:00:00Z",
        )
        result = get_device_row(mock_conn, "BAT001")
        assert result is not None
        assert result["device_id"] == "BAT001"
        assert result["device_type"] == "battery"
        assert result["status"] == "ONLINE"
        assert result["tenant_id"] == "acme"

    def test_returns_none_when_not_found(self, mock_conn) -> None:
        result = get_device_row(mock_conn, "UNKNOWN")
        assert result is None

    def test_tenant_filter_applied(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1, "BAT001", "battery", "Site", "ONLINE",
            "Site", "acme", "2026-01-01T00:00:00Z",
        )
        result = get_device_row(mock_conn, "BAT001", tenant="acme")
        assert result is not None
        execute_args = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args
        params = execute_args[0][1]
        assert "acme" in params


class TestGetFleetCounts:
    """Tests for get_fleet_counts."""

    def test_returns_list_of_counts(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("battery", "ONLINE", 4),
            ("battery", "OFFLINE", 1),
            ("solar_inverter", "ONLINE", 2),
        ]
        result = get_fleet_counts(mock_conn)
        assert len(result) == 3
        assert result[0] == {"device_type": "battery", "status": "ONLINE", "count": 4}

    def test_returns_empty_list(self, mock_conn) -> None:
        result = get_fleet_counts(mock_conn)
        assert result == []

    def test_tenant_filter_applied(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        get_fleet_counts(mock_conn, tenant="acme")
        execute_args = mock_conn.cursor.return_value.__enter__.return_value.execute.call_args
        sql = execute_args[0][0]
        assert "tenant_id" in sql
        assert "acme" in execute_args[0][1]


class TestGetRecentTelemetry:
    """Tests for get_recent_telemetry."""

    def test_returns_telemetry_list(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("2026-06-08T14:35:00Z", "BAT001", 230.0, 15.0, 15.2, 50.1, None, 72.0, None, None, {}),
        ]
        result = get_recent_telemetry(mock_conn, "BAT001", limit=5)
        assert len(result) == 1
        assert result[0]["device_id"] == "BAT001"
        assert result[0]["voltage"] == 230.0
        assert result[0]["battery_soc"] == 72.0


class TestGetDermsRequest:
    """Tests for get_derms_request."""

    def test_returns_derms_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            1, "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "battery_dispatch",
            "Abuja Site A", "BAT001", {"target_soc": 80}, "EXECUTED",
            "2026-06-08T12:00:00Z", "2026-06-08T12:00:05Z",
            "2026-06-08T12:30:00Z", None,
        )
        result = get_derms_request(mock_conn, "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert result is not None
        assert result["request_type"] == "battery_dispatch"
        assert result["status"] == "EXECUTED"
        assert result["params"] == {"target_soc": 80}


class TestGetLastCommand:
    """Tests for get_last_command."""

    def test_returns_command_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            "cmd-001", "discharge", {"power_kw": 10}, "ACKED",
            "2026-06-08T12:00:00Z", "2026-06-08T12:00:01Z",
            "2026-06-08T12:00:02Z", None,
        )
        result = get_last_command(mock_conn, "BAT001")
        assert result is not None
        assert result["command_type"] == "discharge"
        assert result["status"] == "ACKED"

    def test_returns_none_when_no_commands(self, mock_conn) -> None:
        result = get_last_command(mock_conn, "NO_COMMANDS")
        assert result is None


class TestGetDeviceOnboarding:
    """Tests for get_device_onboarding."""

    def test_returns_onboarding_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            "PRODUCTION_READY", "modbus", "Acme Corp",
            {"last_test": "pass"}, "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z",
            "2026-01-04T00:00:00Z",
        )
        result = get_device_onboarding(mock_conn, "BAT001")
        assert result is not None
        assert result["status"] == "PRODUCTION_READY"
        assert result["protocol"] == "modbus"


class TestGetSiteRow:
    """Tests for get_site_row."""

    def test_returns_site_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (
            "Abuja Site A", "commercial", 9.0765, 7.3986, "2026-01-01T00:00:00Z",
        )
        result = get_site_row(mock_conn, "Abuja Site A")
        assert result is not None
        assert result["site_name"] == "Abuja Site A"
        assert result["site_type"] == "commercial"
        assert result["latitude"] == 9.0765


class TestGetCriticalAlarmsCount:
    """Tests for get_critical_alarms_count."""

    def test_returns_count(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (3,)
        result = get_critical_alarms_count(mock_conn, tenant="acme")
        assert result == 3

    def test_returns_zero(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (0,)
        result = get_critical_alarms_count(mock_conn, tenant="acme")
        assert result == 0


class TestGet24hAlarmTrend:
    """Tests for get_24h_alarm_trend."""

    def test_returns_trend_dict(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (3, 2)
        result = get_24h_alarm_trend(mock_conn, tenant="acme")
        assert result == {"current": 3, "previous": 2}


class TestGetOfflineTrend:
    """Tests for get_offline_trend."""

    def test_returns_trend_dict(self, mock_conn) -> None:
        # Two queries: current and previous
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.side_effect = [
            (2,),  # current
            (1,),  # previous
        ]
        result = get_offline_trend(mock_conn, tenant="acme")
        assert result == {"current": 2, "previous": 1}


class TestGetDeviceCertifications:
    """Tests for get_device_certifications."""

    def test_returns_certifications(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            ("safety_test", "PASS", "All safety checks passed", "2026-01-01T00:00:00Z"),
            ("protocol_test", "PASS", "Modbus protocol validated", "2026-01-02T00:00:00Z"),
        ]
        result = get_device_certifications(mock_conn, "BAT001")
        assert len(result) == 2
        assert result[0]["test_name"] == "safety_test"

    def test_returns_empty_list(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_device_certifications(mock_conn, "UNKNOWN")
        assert result == []


class TestGetDermsActionsByDeviceAndTime:
    """Tests for get_derms_actions_by_device_and_time."""

    def test_returns_actions(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = [
            (1, "a1b2c3d4", "battery_dispatch", "Site A", "BAT001", 
             {"target_soc": 80}, "EXECUTED", "2026-01-01T00:00:00Z", 
             "2026-01-01T00:05:00Z", "2026-01-01T00:30:00Z"),
        ]
        result = get_derms_actions_by_device_and_time(
            mock_conn, "BAT001", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"
        )
        assert len(result) == 1
        assert result[0]["request_type"] == "battery_dispatch"

    def test_returns_empty_list(self, mock_conn) -> None:
        mock_conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_derms_actions_by_device_and_time(
            mock_conn, "UNKNOWN", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"
        )
        assert result == []


__all__ = [
    "TestGetAlarmById",
    "TestGetDeviceRow",
    "TestGetFleetCounts",
    "TestGetRecentTelemetry",
    "TestGetDermsRequest",
    "TestGetLastCommand",
    "TestGetDeviceOnboarding",
    "TestGetSiteRow",
    "TestGetCriticalAlarmsCount",
    "TestGet24hAlarmTrend",
    "TestGetOfflineTrend",
    "TestGetDeviceCertifications",
    "TestGetDermsActionsByDeviceAndTime",
]