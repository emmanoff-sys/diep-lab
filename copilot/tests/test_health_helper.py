"""Unit tests for ``health_helper`` device health evaluation."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from copilot.helpers.health_helper import (
    evaluate_health_for_device,
    evaluate_health_bulk,
    is_device_healthy,
    get_top_concerns,
)


class TestEvaluateHealthForDevice:
    """Tests for ``evaluate_health_for_device()``."""

    def test_online_device_with_fresh_telemetry(self) -> None:
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat(), "power_kw": "15"}
        result = evaluate_health_for_device("BAT001", device_row, device_state)
        assert result["health"] == "OK"
        assert result["is_online"] is True
        assert result["has_critical_alarm"] is False

    def test_offline_device_registry(self) -> None:
        device_row = {"device_id": "BAT002", "status": "OFFLINE"}
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat()}
        result = evaluate_health_for_device("BAT002", device_row, device_state)
        assert result["health"] == "OFFLINE"
        assert result["is_online"] is False
        assert "offline" in result["reason"].lower()

    def test_degraded_device_registry(self) -> None:
        device_row = {"device_id": "INV003", "status": "DEGRADED"}
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat()}
        result = evaluate_health_for_device("INV003", device_row, device_state)
        assert result["health"] == "DEGRADED"
        assert result["is_online"] is False

    def test_stale_telemetry_degraded(self) -> None:
        device_row = {"device_id": "MTR001", "status": "ONLINE"}
        # Telemetry from 15 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        device_state = {"last_seen": old_time.isoformat()}
        result = evaluate_health_for_device("MTR001", device_row, device_state)
        assert result["health"] == "DEGRADED"
        assert result["is_online"] is False
        assert result["telemetry_fresh"] is False
        assert "stale" in result["reason"].lower()

    def test_critical_alarm_degraded(self) -> None:
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat()}
        recent_alarms = [
            {"severity": "CRITICAL", "alarm_type": "over_voltage"},
        ]
        result = evaluate_health_for_device(
            "BAT001", device_row, device_state, recent_alarms=recent_alarms
        )
        assert result["health"] == "DEGRADED"
        assert result["has_critical_alarm"] is True
        assert result["is_online"] is False

    def test_high_alarm_degraded(self) -> None:
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat()}
        recent_alarms = [
            {"severity": "HIGH", "alarm_type": "frequency_anomaly"},
        ]
        result = evaluate_health_for_device(
            "BAT001", device_row, device_state, recent_alarms=recent_alarms
        )
        assert result["health"] == "DEGRADED"
        assert result["has_critical_alarm"] is True

    def test_no_device_row(self) -> None:
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat()}
        result = evaluate_health_for_device("UNKNOWN", None, device_state)
        # No registry status → should check telemetry
        assert result["health"] in ("OK", "UNKNOWN")

    def test_no_device_state(self) -> None:
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        result = evaluate_health_for_device("BAT001", device_row, None)
        assert result["health"] == "OK"
        assert "No device state data available" in result["reason"]

    def test_no_last_seen_in_state(self) -> None:
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        device_state = {"power_kw": "15", "battery_soc": "72"}
        result = evaluate_health_for_device("BAT001", device_row, device_state)
        assert result["health"] == "OK"
        assert result["telemetry_fresh"] is None

    def test_barely_fresh_telemetry(self) -> None:
        """Telemetry at 4.5 minutes (under 5 min threshold) should be fresh."""
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        recent = datetime.now(timezone.utc) - timedelta(seconds=270)  # 4.5 min
        device_state = {"last_seen": recent.isoformat()}
        result = evaluate_health_for_device("BAT001", device_row, device_state)
        assert result["health"] == "OK"
        assert result["telemetry_fresh"] is True

    def test_marginally_stale_telemetry(self) -> None:
        """Telemetry at 7 minutes (over 5 min, under 10 min) should degrade."""
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        recent = datetime.now(timezone.utc) - timedelta(seconds=420)  # 7 min
        device_state = {"last_seen": recent.isoformat()}
        result = evaluate_health_for_device("BAT001", device_row, device_state)
        assert result["health"] == "DEGRADED"
        assert result["telemetry_fresh"] is False
        assert "No recent telemetry" in result["reason"]

    def test_info_alarm_does_not_degrade(self) -> None:
        """INFO and WARNING alarms should not cause DEGRADED status."""
        device_row = {"device_id": "BAT001", "status": "ONLINE"}
        device_state = {"last_seen": datetime.now(timezone.utc).isoformat()}
        recent_alarms = [
            {"severity": "INFO", "alarm_type": "telemetry_gap"},
            {"severity": "WARNING", "alarm_type": "low_battery"},
        ]
        result = evaluate_health_for_device(
            "BAT001", device_row, device_state, recent_alarms=recent_alarms
        )
        assert result["health"] == "OK"
        assert result["has_critical_alarm"] is False


class TestEvaluateHealthBulk:
    """Tests for ``evaluate_health_bulk()``."""

    def test_bulk_evaluation_returns_dict_by_device_id(self) -> None:
        device_rows = [
            {"device_id": "BAT001", "status": "ONLINE"},
            {"device_id": "BAT002", "status": "OFFLINE"},
        ]
        device_states = {
            "BAT001": {"last_seen": datetime.now(timezone.utc).isoformat()},
            "BAT002": {"last_seen": datetime.now(timezone.utc).isoformat()},
        }
        result = evaluate_health_bulk(device_rows, device_states)
        assert "BAT001" in result
        assert "BAT002" in result
        assert result["BAT001"]["health"] == "OK"
        assert result["BAT002"]["health"] == "OFFLINE"

    def test_bulk_with_alarms(self) -> None:
        device_rows = [
            {"device_id": "BAT001", "status": "ONLINE"},
        ]
        device_states = {
            "BAT001": {"last_seen": datetime.now(timezone.utc).isoformat()},
        }
        alarms = {
            "BAT001": [{"severity": "CRITICAL", "alarm_type": "over_voltage"}],
        }
        result = evaluate_health_bulk(device_rows, device_states, alarms_by_device=alarms)
        assert result["BAT001"]["has_critical_alarm"] is True

    def test_bulk_empty_devices(self) -> None:
        result = evaluate_health_bulk([], {})
        assert result == {}


class TestIsDeviceHealthy:
    """Tests for ``is_device_healthy()``."""

    def test_ok_device(self) -> None:
        assert is_device_healthy({"health": "OK", "reason": ""}) is True

    def test_degraded_device(self) -> None:
        assert is_device_healthy({"health": "DEGRADED", "reason": ""}) is False

    def test_offline_device(self) -> None:
        assert is_device_healthy({"health": "OFFLINE", "reason": ""}) is False

    def test_unknown_device(self) -> None:
        assert is_device_healthy({"health": "UNKNOWN", "reason": ""}) is False


class TestGetTopConcerns:
    """Tests for ``get_top_concerns()``."""

    def test_returns_top_n_concerns(self) -> None:
        health_map = {
            "BAT001": {"health": "OK", "has_critical_alarm": False, "telemetry_fresh": True, "reason": "OK"},
            "BAT002": {"health": "OFFLINE", "has_critical_alarm": False, "telemetry_fresh": True, "reason": "Offline"},
            "INV003": {"health": "DEGRADED", "has_critical_alarm": True, "telemetry_fresh": False, "reason": "Critical alarm"},
            "MTR004": {"health": "DEGRADED", "has_critical_alarm": False, "telemetry_fresh": False, "reason": "Stale telemetry"},
        }
        concerns = get_top_concerns(health_map, top_n=3)
        assert len(concerns) == 3
        # INV003 has highest score (critical alarm) → should be first
        assert concerns[0]["device_id"] == "INV003"
        assert concerns[0]["health"] == "DEGRADED"

    def test_returns_all_when_less_than_top_n(self) -> None:
        health_map = {
            "BAT001": {"health": "OFFLINE", "has_critical_alarm": False, "telemetry_fresh": True, "reason": ""},
        }
        concerns = get_top_concerns(health_map, top_n=5)
        assert len(concerns) == 1

    def test_returns_empty_when_no_devices(self) -> None:
        concerns = get_top_concerns({}, top_n=5)
        assert concerns == []

    def test_prioritizes_critical_alarms_over_offline(self) -> None:
        health_map = {
            "BAT001": {"health": "OK", "has_critical_alarm": True, "telemetry_fresh": True, "reason": "Critical"},
            "BAT002": {"health": "OFFLINE", "has_critical_alarm": False, "telemetry_fresh": True, "reason": "Offline"},
        }
        concerns = get_top_concerns(health_map, top_n=2)
        assert concerns[0]["device_id"] == "BAT001"  # critical alarm first
        assert concerns[1]["device_id"] == "BAT002"  # offline second

    def test_prioritizes_offline_over_degraded(self) -> None:
        health_map = {
            "BAT001": {"health": "DEGRADED", "has_critical_alarm": False, "telemetry_fresh": False, "reason": "Stale"},
            "BAT002": {"health": "OFFLINE", "has_critical_alarm": False, "telemetry_fresh": True, "reason": "Offline"},
        }
        concerns = get_top_concerns(health_map, top_n=2)
        assert concerns[0]["device_id"] == "BAT002"  # offline first
        assert concerns[1]["device_id"] == "BAT001"  # degraded second