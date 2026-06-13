"""Inline device health evaluation for the Copilot service.

Provides ``evaluate_health()`` and ``evaluate_health_for_device()`` functions
that assess a device's operational status based on Redis state, telemetry
freshness, and alarm activity.

This is additive logic — it does not modify any existing health evaluation in
``fastapi/app.py`` or anywhere else in the platform.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("diep-copilot.health_helper")

# How recent telemetry must be for a device to be considered "online" (seconds).
TELEMETRY_FRESHNESS_SECONDS = 300  # 5 minutes

# How recent telemetry must be for a device to be considered "degraded" (seconds).
TELEMETRY_STALE_SECONDS = 600  # 10 minutes


def evaluate_health_for_device(
    device_id: str,
    device_row: dict[str, Any] | None,
    device_state: dict[str, Any] | None,
    recent_alarms: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assess the health status of a single device.

    Uses a combination of signals:
      1. Device registry status (ONLINE/OFFLINE/DEGRADED/UNKNOWN).
      2. Redis state freshness (``last_seen`` field).
      3. Active critical/high alarms.

    Args:
        device_id: The device identifier.
        device_row: Device registry row (from ``db_queries.get_device_row``).
        device_state: Current Redis state hash (from ``redis.hgetall``).
        recent_alarms: Recent alarms for this device (from
            ``db_queries.get_alarms_by_device`` with a small limit).

    Returns:
        Dict with keys:
            - ``health``: One of ``"OK"``, ``"DEGRADED"``, ``"OFFLINE"``,
              ``"UNKNOWN"``.
            - ``reason``: Human-readable explanation of the health assessment.
            - ``is_online``: Boolean convenience flag.
            - ``has_critical_alarm``: Boolean.
            - ``telemetry_fresh``: Boolean or None if no state available.
    """
    reason_parts: list[str] = []
    has_critical = False
    telemetry_fresh: bool | None = None

    # 1. Check device registry status.
    registry_status = (device_row or {}).get("status", "UNKNOWN")

    if registry_status == "OFFLINE":
        reason_parts.append("Device registry reports offline")
    elif registry_status == "DEGRADED":
        reason_parts.append("Device registry reports degraded")
    elif registry_status == "UNKNOWN":
        reason_parts.append("Device registry status is unknown")

    # 2. Check Redis state freshness.
    last_seen_str = (device_state or {}).get("last_seen")
    if last_seen_str:
        try:
            last_seen = _parse_timestamp(last_seen_str)
            now = datetime.now(timezone.utc)
            age_seconds = (now - last_seen).total_seconds()
            if age_seconds < TELEMETRY_FRESHNESS_SECONDS:
                telemetry_fresh = True
            elif age_seconds < TELEMETRY_STALE_SECONDS:
                telemetry_fresh = False
                reason_parts.append(f"No recent telemetry in {int(age_seconds)}s")
            else:
                telemetry_fresh = False
                reason_parts.append(
                    f"Stale telemetry (last seen {int(age_seconds)}s ago)"
                )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Cannot parse last_seen for device %s: %s", device_id, exc
            )
            telemetry_fresh = None
    else:
        telemetry_fresh = None
        if device_state:
            reason_parts.append("No last_seen in device state")

    # 3. Check for critical/high alarms.
    if recent_alarms:
        critical_alarms = [
            a
            for a in recent_alarms
            if a.get("severity", "").upper() in ("CRITICAL", "HIGH")
        ]
        if critical_alarms:
            has_critical = True
            reasons = {a.get("alarm_type", "unknown") for a in critical_alarms}
            reason_parts.append(
                f"Active critical/high alarms: {', '.join(reasons)}"
            )

    # 4. Determine final health status.
    if registry_status == "OFFLINE":
        health = "OFFLINE"
    elif registry_status == "DEGRADED":
        health = "DEGRADED"
    elif has_critical:
        health = "DEGRADED"
    elif telemetry_fresh is False:
        health = "DEGRADED"
    elif telemetry_fresh is True and registry_status == "ONLINE":
        health = "OK"
    elif registry_status == "ONLINE" and telemetry_fresh is None:
        # Online in registry but no state data — assume OK with caveat.
        health = "OK"
        reason_parts.append("No device state data available")
    else:
        health = registry_status

    reason = "; ".join(reason_parts) if reason_parts else "Device is operating normally"

    return {
        "health": health,
        "reason": reason,
        "is_online": health == "OK",
        "has_critical_alarm": has_critical,
        "telemetry_fresh": telemetry_fresh,
    }


def evaluate_health_bulk(
    device_rows: list[dict[str, Any]],
    device_states: dict[str, dict[str, Any]],
    alarms_by_device: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Bulk evaluate health for multiple devices.

    More efficient than calling ``evaluate_health_for_device`` in a loop for
    fleet-wide assessments.

    Args:
        device_rows: List of device row dicts (must include `device_id`).
        device_states: Mapping of device_id -> Redis state hash.
        alarms_by_device: Optional mapping of device_id -> list of recent alarms.

    Returns:
        Mapping of device_id -> health assessment dict.
    """
    result: dict[str, dict[str, Any]] = {}
    alarms_by_device = alarms_by_device or {}

    for device_row in device_rows:
        device_id = device_row["device_id"]
        state = device_states.get(device_id, {})
        alarms = alarms_by_device.get(device_id, [])
        result[device_id] = evaluate_health_for_device(
            device_id=device_id,
            device_row=device_row,
            device_state=state,
            recent_alarms=alarms,
        )

    return result


def is_device_healthy(health: dict[str, Any]) -> bool:
    """Convenience predicate: returns True if device is OK (not degraded/offline).

    Args:
        health: Health dict returned by ``evaluate_health_for_device``.

    Returns:
        True if health status is ``"OK"``.
    """
    return health.get("health") == "OK"


def get_top_concerns(
    device_health_map: dict[str, dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Sort devices by concern severity and return the top N.

    Sorting priority:
      1. Devices with critical alarms.
      2. OFFLINE devices.
      3. DEGRADED devices.
      4. Devices with stale telemetry.
      5. Alphabetical by device_id (tiebreaker).

    Args:
        device_health_map: Mapping of device_id -> health assessment dict.
        top_n: Max number of concerns to return.

    Returns:
        List of dicts with keys (device_id, health, reason), sorted by severity.
    """
    scored: list[tuple[int, str, dict[str, Any]]] = []

    for device_id, health in device_health_map.items():
        score = 0
        if health.get("has_critical_alarm"):
            score += 1000
        if health["health"] == "OFFLINE":
            score += 500
        elif health["health"] == "DEGRADED":
            score += 200
        if health.get("telemetry_fresh") is False:
            score += 50

        # Use negative device_id for deterministic ordering of ties.
        scored.append((-score, device_id, health))

    scored.sort(key=lambda x: (x[0], x[1]))
    top = scored[:top_n]

    return [
        {
            "device_id": device_id,
            "health": health["health"],
            "reason": health["reason"],
        }
        for _, device_id, health in top
    ]


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime.

    Args:
        ts_str: ISO 8601 string (e.g., ``"2026-06-08T14:35:00Z"`` or
            ``"2026-06-08T14:35:00+00:00"``).

    Returns:
        Timezone-aware datetime.

    Raises:
        ValueError: If the timestamp cannot be parsed.
    """
    # Handle trailing Z
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


__all__ = [
    "evaluate_health_for_device",
    "evaluate_health_bulk",
    "is_device_healthy",
    "get_top_concerns",
]