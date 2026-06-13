"""Parameterised SQL query functions for the Copilot service.

All functions accept an optional ``tenant`` parameter and apply tenant filtering
via ``apply_tenant_filter()``. All queries use ``psycopg2`` ``%s`` placeholders
— never string interpolation with user input.

Every function returns raw row data as dictionaries (or lists of dicts) that the
caller can use for prompt assembly or health evaluation.
"""

from __future__ import annotations

import logging
from typing import Any

from copilot.helpers.tenant_filter import apply_tenant_filter

logger = logging.getLogger("diep-copilot.db_queries")

# ──────────────────────────────────────────────────────────────────────────────
# Alarm queries
# ──────────────────────────────────────────────────────────────────────────────


def get_alarm_by_id(
    conn,
    alarm_id: int,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    """Fetch a single alarm row by primary key.

    Args:
        conn: psycopg2 connection (or connection-like).
        alarm_id: Primary key of the alarms table.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        Alarm dict with keys (id, device_id, alarm_type, severity, message,
        metadata, raised_at), or None if not found.
    """
    base = """
        SELECT a.id, a.device_id, a.alarm_type, a.severity, a.message,
               a.metadata, a.raised_at
        FROM alarms a
        JOIN devices d ON a.device_id = d.device_id
        WHERE a.id = %s
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    params = [alarm_id]
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "device_id": row[1],
            "alarm_type": row[2],
            "severity": row[3],
            "message": row[4],
            "metadata": row[5],
            "raised_at": row[6].isoformat() if hasattr(row[6], "isoformat") else row[6],
        }


def get_alarms_by_device(
    conn,
    device_id: str,
    limit: int = 50,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch recent alarms for a specific device.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.
        limit: Max rows to return.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        List of alarm dicts ordered by raised_at DESC.
    """
    base = """
        SELECT a.id, a.device_id, a.alarm_type, a.severity, a.message,
               a.metadata, a.raised_at
        FROM alarms a
        JOIN devices d ON a.device_id = d.device_id
        WHERE d.device_id = %s
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    query += " ORDER BY a.raised_at DESC LIMIT %s"
    params = [device_id]
    if tenant is not None:
        params.append(tenant)
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "device_id": r[1],
                "alarm_type": r[2],
                "severity": r[3],
                "message": r[4],
                "metadata": r[5],
                "raised_at": r[6].isoformat() if hasattr(r[6], "isoformat") else r[6],
            }
            for r in rows
        ]


def get_alarms_by_site(
    conn,
    site_name: str,
    limit: int = 50,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch recent alarms for all devices at a given site.

    Args:
        conn: psycopg2 connection.
        site_name: The site name.
        limit: Max rows to return.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        List of alarm dicts ordered by raised_at DESC.
    """
    base = """
        SELECT a.id, a.device_id, a.alarm_type, a.severity, a.message,
               a.metadata, a.raised_at
        FROM alarms a
        JOIN devices d ON a.device_id = d.device_id
        WHERE d.site_name = %s
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    query += " ORDER BY a.raised_at DESC LIMIT %s"
    params = [site_name]
    if tenant is not None:
        params.append(tenant)
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "device_id": r[1],
                "alarm_type": r[2],
                "severity": r[3],
                "message": r[4],
                "metadata": r[5],
                "raised_at": r[6].isoformat() if hasattr(r[6], "isoformat") else r[6],
            }
            for r in rows
        ]


def get_critical_alarms_count(
    conn,
    tenant: str | None = None,
) -> int:
    """Count active CRITICAL and HIGH severity alarms for a tenant.

    Args:
        conn: psycopg2 connection.
        tenant: Tenant ID (required for tenant-scoped access, None for global).

    Returns:
        Integer count.
    """
    base = """
        SELECT COUNT(*) AS count
        FROM alarms a
        JOIN devices d ON a.device_id = d.device_id
        WHERE a.severity IN ('CRITICAL', 'HIGH')
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    params = []
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else 0


def get_24h_alarm_trend(
    conn,
    tenant: str | None = None,
) -> dict[str, int]:
    """Compare alarm counts: current 24h vs previous 24h window.

    Args:
        conn: psycopg2 connection.
        tenant: Tenant ID.

    Returns:
        Dict with keys ``current`` and ``previous`` (integer counts).
    """
    base = """
        SELECT
            COUNT(*) FILTER (WHERE a.raised_at > now() - interval '24 hours') AS current,
            COUNT(*) FILTER (
                WHERE a.raised_at BETWEEN now() - interval '48 hours'
                    AND now() - interval '24 hours'
            ) AS previous
        FROM alarms a
        JOIN devices d ON a.device_id = d.device_id
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    params = []
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return {"current": 0, "previous": 0}
        return {"current": row[0] or 0, "previous": row[1] or 0}


# ──────────────────────────────────────────────────────────────────────────────
# Device queries
# ──────────────────────────────────────────────────────────────────────────────


def get_device_row(
    conn,
    device_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    """Fetch a device row by device_id.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        Device dict with keys (id, device_id, device_type, location, status,
        site_name, tenant_id, created_at), or None if not found.
    """
    base = "SELECT id, device_id, device_type, location, status, site_name, tenant_id, created_at FROM devices d WHERE d.device_id = %s"
    query = apply_tenant_filter(base, tenant, alias="d")
    params = [device_id]
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "device_id": row[1],
            "device_type": row[2],
            "location": row[3],
            "status": row[4],
            "site_name": row[5],
            "tenant_id": row[6],
            "created_at": row[7].isoformat() if hasattr(row[7], "isoformat") else row[7],
        }


def get_fleet_counts(
    conn,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate device counts grouped by device_type and status.

    Args:
        conn: psycopg2 connection.
        tenant: Tenant ID.

    Returns:
        List of dicts with keys (device_type, status, count).
    """
    base = """
        SELECT d.device_type, d.status, COUNT(*) AS count
        FROM devices d
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    query += " GROUP BY d.device_type, d.status ORDER BY d.device_type, d.status"
    params = []
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {"device_type": r[0], "status": r[1], "count": r[2]}
            for r in rows
        ]


def get_devices_by_site(
    conn,
    site_name: str,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    """List all devices at a given site.

    Args:
        conn: psycopg2 connection.
        site_name: The site name.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        List of device dicts (id, device_id, device_type, status, location).
    """
    base = """
        SELECT id, device_id, device_type, status, location
        FROM devices d
        WHERE d.site_name = %s
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    query += " ORDER BY d.device_id"
    params = [site_name]
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "device_id": r[1],
                "device_type": r[2],
                "status": r[3],
                "location": r[4],
            }
            for r in rows
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Telemetry queries
# ──────────────────────────────────────────────────────────────────────────────


def get_recent_telemetry(
    conn,
    device_id: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Fetch the most recent telemetry rows for a device.

    NOTE: Telemetry is not tenant-scoped directly; it is scoped by device_id.
    The caller is responsible for ensuring the device_id itself is tenant-filtered.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.
        limit: Max rows to return.

    Returns:
        List of telemetry dicts ordered by time DESC, each containing:
        time, device_id, voltage, current, power_kw, frequency, solar_kw,
        battery_soc, grid_import_kw, grid_export_kw, metadata.
    """
    query = """
        SELECT time, device_id, voltage, current, power_kw, frequency,
               solar_kw, battery_soc, grid_import_kw, grid_export_kw, metadata
        FROM telemetry
        WHERE device_id = %s
        ORDER BY time DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (device_id, limit))
        rows = cur.fetchall()
        return [
            {
                "time": r[0].isoformat() if hasattr(r[0], "isoformat") else r[0],
                "device_id": r[1],
                "voltage": r[2],
                "current": r[3],
                "power_kw": r[4],
                "frequency": r[5],
                "solar_kw": r[6],
                "battery_soc": r[7],
                "grid_import_kw": r[8],
                "grid_export_kw": r[9],
                "metadata": r[10],
            }
            for r in rows
        ]


# ──────────────────────────────────────────────────────────────────────────────
# DERMS request queries
# ──────────────────────────────────────────────────────────────────────────────


def get_derms_request(
    conn,
    request_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    """Fetch a single DERMS request by request_id (UUID string).

    Args:
        conn: psycopg2 connection.
        request_id: UUID of the DERMS request.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        DERMS request dict, or None.
    """
    base = """
        SELECT dr.id, dr.request_id, dr.request_type, dr.site_name,
               dr.device_id, dr.params, dr.status, dr.created_at,
               dr.executed_at, dr.completed_at, dr.error_message
        FROM derms_requests dr
        JOIN devices d ON dr.device_id = d.device_id
        WHERE dr.request_id = %s
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    params = [request_id]
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "request_id": str(row[1]),
            "request_type": row[2],
            "site_name": row[3],
            "device_id": row[4],
            "params": row[5],
            "status": row[6],
            "created_at": row[7].isoformat() if hasattr(row[7], "isoformat") else row[7],
            "executed_at": row[8].isoformat() if row[8] and hasattr(row[8], "isoformat") else row[8],
            "completed_at": row[9].isoformat() if row[9] and hasattr(row[9], "isoformat") else row[9],
            "error_message": row[10],
        }


def get_derms_actions_by_device_and_time(
    conn,
    device_id: str,
    window_start,
    window_end,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch DERMS actions for a device within a time window.

    Used for explain_alarm to show DERMS actions in ±30min of alarm time.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.
        window_start: Start of time window (datetime or ISO string).
        window_end: End of time window (datetime or ISO string).
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        List of DERMS request dicts.
    """
    base = """
        SELECT dr.id, dr.request_id, dr.request_type, dr.site_name,
               dr.device_id, dr.params, dr.status, dr.created_at,
               dr.executed_at, dr.completed_at
        FROM derms_requests dr
        JOIN devices d ON dr.device_id = d.device_id
        WHERE dr.device_id = %s AND dr.created_at BETWEEN %s AND %s
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    query += " ORDER BY dr.created_at DESC"
    params = [device_id, window_start, window_end]
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "request_id": str(r[1]),
                "request_type": r[2],
                "site_name": r[3],
                "device_id": r[4],
                "params": r[5],
                "status": r[6],
                "created_at": r[7].isoformat() if hasattr(r[7], "isoformat") else r[7],
                "executed_at": r[8].isoformat() if r[8] and hasattr(r[8], "isoformat") else r[8],
                "completed_at": r[9].isoformat() if r[9] and hasattr(r[9], "isoformat") else r[9],
            }
            for r in rows
        ]


def get_active_derms_by_site(
    conn,
    site_name: str,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch active (non-terminal) DERMS requests for a site.

    Args:
        conn: psycopg2 connection.
        site_name: The site name.
        tenant: Optional tenant ID for isolation filtering.

    Returns:
        List of active DERMS request dicts.
    """
    base = """
        SELECT dr.request_id, dr.request_type, dr.status, dr.created_at,
               dr.device_id, dr.params
        FROM derms_requests dr
        JOIN devices d ON dr.device_id = d.device_id
        WHERE dr.site_name = %s AND dr.status NOT IN ('COMPLETED', 'FAILED')
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    query += " ORDER BY dr.created_at DESC"
    params = [site_name]
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "request_id": str(r[0]),
                "request_type": r[1],
                "status": r[2],
                "created_at": r[3].isoformat() if hasattr(r[3], "isoformat") else r[3],
                "device_id": r[4],
                "params": r[5],
            }
            for r in rows
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Command queries
# ──────────────────────────────────────────────────────────────────────────────


def get_last_command(
    conn,
    device_id: str,
) -> dict[str, Any] | None:
    """Fetch the most recent command for a device.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.

    Returns:
        Command dict (command_id, command_type, params, status, created_at,
        dispatched_at, acked_at, error_message), or None.
    """
    query = """
        SELECT command_id, command_type, params, status, created_at,
               dispatched_at, acked_at, error_message
        FROM commands
        WHERE device_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (device_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "command_id": str(row[0]),
            "command_type": row[1],
            "params": row[2],
            "status": row[3],
            "created_at": row[4].isoformat() if hasattr(row[4], "isoformat") else row[4],
            "dispatched_at": row[5].isoformat() if row[5] and hasattr(row[5], "isoformat") else row[5],
            "acked_at": row[6].isoformat() if row[6] and hasattr(row[6], "isoformat") else row[6],
            "error_message": row[7],
        }


def get_command_by_device_and_time(
    conn,
    device_id: str,
    approximate_created_at,
) -> dict[str, Any] | None:
    """Fetch the command closest to a given timestamp for a device.

    Used for explain_derms_action to correlate a DERMS request with the
    dispatched command.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.
        approximate_created_at: Approximate command creation time.

    Returns:
        Command dict, or None.
    """
    query = """
        SELECT command_id, command_type, params, status, created_at,
               dispatched_at, acked_at, error_message
        FROM commands
        WHERE device_id = %s
          AND created_at BETWEEN %s - interval '5 minutes' AND %s + interval '5 minutes'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at) - EXTRACT(EPOCH FROM %s::timestamptz))
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (device_id, approximate_created_at, approximate_created_at, approximate_created_at))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "command_id": str(row[0]),
            "command_type": row[1],
            "params": row[2],
            "status": row[3],
            "created_at": row[4].isoformat() if hasattr(row[4], "isoformat") else row[4],
            "dispatched_at": row[5].isoformat() if row[5] and hasattr(row[5], "isoformat") else row[5],
            "acked_at": row[6].isoformat() if row[6] and hasattr(row[6], "isoformat") else row[6],
            "error_message": row[7],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Device onboarding & certification queries
# ──────────────────────────────────────────────────────────────────────────────


def get_device_onboarding(
    conn,
    device_id: str,
) -> dict[str, Any] | None:
    """Fetch onboarding status for a device.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.

    Returns:
        Onboarding dict (status, protocol, vendor, validation, registered_at,
        validated_at, certified_at, production_approved_at), or None.
    """
    query = """
        SELECT status, protocol, vendor, validation, registered_at,
               validated_at, certified_at, production_approved_at
        FROM device_onboarding
        WHERE device_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (device_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "status": row[0],
            "protocol": row[1],
            "vendor": row[2],
            "validation": row[3],
            "registered_at": row[4].isoformat() if hasattr(row[4], "isoformat") else row[4],
            "validated_at": row[5].isoformat() if row[5] and hasattr(row[5], "isoformat") else row[5],
            "certified_at": row[6].isoformat() if row[6] and hasattr(row[6], "isoformat") else row[6],
            "production_approved_at": row[7].isoformat() if row[7] and hasattr(row[7], "isoformat") else row[7],
        }


def get_device_certifications(
    conn,
    device_id: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Fetch the most recent certification test results for a device.

    Args:
        conn: psycopg2 connection.
        device_id: The device identifier.
        limit: Max rows to return (default 6 for 6 standard tests).

    Returns:
        List of certification dicts (test_name, result, details, run_at).
    """
    query = """
        SELECT test_name, result, details, run_at
        FROM device_certifications
        WHERE device_id = %s
        ORDER BY run_at DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (device_id, limit))
        rows = cur.fetchall()
        return [
            {
                "test_name": r[0],
                "result": r[1],
                "details": r[2],
                "run_at": r[3].isoformat() if hasattr(r[3], "isoformat") else r[3],
            }
            for r in rows
        ]


# ──────────────────────────────────────────────────────────────────────────────
# Site queries
# ──────────────────────────────────────────────────────────────────────────────


def get_site_row(
    conn,
    site_name: str,
) -> dict[str, Any] | None:
    """Fetch site metadata.

    Args:
        conn: psycopg2 connection.
        site_name: The site name.

    Returns:
        Site dict (site_name, site_type, latitude, longitude, created_at), or None.
    """
    query = """
        SELECT site_name, site_type, latitude, longitude, created_at
        FROM sites
        WHERE site_name = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (site_name,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "site_name": row[0],
            "site_type": row[1],
            "latitude": float(row[2]) if row[2] is not None else None,
            "longitude": float(row[3]) if row[3] is not None else None,
            "created_at": row[4].isoformat() if hasattr(row[4], "isoformat") else row[4],
        }


def get_total_offline_count(
    conn,
    tenant: str | None = None,
) -> int:
    """Count OFFLINE devices for a tenant.

    Args:
        conn: psycopg2 connection.
        tenant: Tenant ID.

    Returns:
        Integer count.
    """
    base = "SELECT COUNT(*) FROM devices d WHERE d.status = 'OFFLINE'"
    query = apply_tenant_filter(base, tenant, alias="d")
    params = []
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return row[0] if row else 0


def get_offline_trend(
    conn,
    tenant: str | None = None,
) -> dict[str, int]:
    """Compare offline device counts: current vs previous 24h.

    Uses the devices table created_at as a proxy for offline status deltas.
    For a more accurate trend, this would need a device_status_history table,
    but for Sprint 2 we approximate via telemetry freshness.

    Args:
        conn: psycopg2 connection.
        tenant: Tenant ID.

    Returns:
        Dict with ``current`` (alarm-based) and ``previous`` counts.
    """
    # Count devices that have no telemetry in the last 5 minutes as "effectively offline"
    base = """
        SELECT COUNT(*) AS current
        FROM devices d
        WHERE d.device_id NOT IN (
            SELECT DISTINCT device_id
            FROM telemetry
            WHERE time > now() - interval '5 minutes'
        )
    """
    query = apply_tenant_filter(base, tenant, alias="d")
    params = []
    if tenant is not None:
        params.append(tenant)

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        current = row[0] if row else 0

    base_prev = """
        SELECT COUNT(*) AS previous
        FROM devices d
        WHERE d.device_id NOT IN (
            SELECT DISTINCT device_id
            FROM telemetry
            WHERE time BETWEEN now() - interval '24 hours' AND now() - interval '5 minutes'
        )
    """
    query_prev = apply_tenant_filter(base_prev, tenant, alias="d")
    with conn.cursor() as cur:
        cur.execute(query_prev, params)
        row = cur.fetchone()
        previous = row[0] if row else 0

    return {"current": current, "previous": previous}


__all__ = [
    "get_alarm_by_id",
    "get_alarms_by_device",
    "get_alarms_by_site",
    "get_critical_alarms_count",
    "get_24h_alarm_trend",
    "get_device_row",
    "get_fleet_counts",
    "get_devices_by_site",
    "get_recent_telemetry",
    "get_derms_request",
    "get_derms_actions_by_device_and_time",
    "get_active_derms_by_site",
    "get_last_command",
    "get_command_by_device_and_time",
    "get_device_onboarding",
    "get_device_certifications",
    "get_site_row",
    "get_total_offline_count",
    "get_offline_trend",
]