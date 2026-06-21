"""ADMS M5a — Historian module.

Formalizes the existing TimescaleDB telemetry store (hypertable + telemetry_1m /
telemetry_1h continuous aggregates + compression/retention policies from
sql/010) as a named "Historian" with a documented query API and retention
introspection. No new storage — a clean read facade over what already exists.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query

import common
from auth import require_role

router = APIRouter(prefix="/historian", tags=["historian"])

READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")

# Whitelisted metrics (column names are interpolated, so this guards injection).
RAW_METRICS = {
    "power_kw", "voltage", "current", "frequency", "solar_kw", "battery_soc",
    "grid_import_kw", "grid_export_kw", "temperature", "power_factor",
}
# Continuous aggregates expose avg_<metric> for this subset.
AGG_METRICS = {
    "power_kw", "voltage", "frequency", "solar_kw", "battery_soc",
    "temperature", "power_factor",
}
BUCKET_VIEW = {"1m": "telemetry_1m", "1h": "telemetry_1h"}


@router.get("/query")
def query(
    device_id: str = Query(..., examples=["BAT001"]),
    metric: str = Query("power_kw"),
    bucket: str = Query("raw", description="raw | 1m | 1h"),
    hours: float = Query(24, gt=0, le=24 * 90, description="lookback window in hours"),
    _p=Depends(require_role(*READ_ROLES)),
):
    """Time series for one device+metric over a lookback window. `raw` reads the
    telemetry hypertable; `1m`/`1h` read the continuous aggregates (avg_<metric>)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    if bucket == "raw":
        if metric not in RAW_METRICS:
            raise HTTPException(status_code=422, detail=f"unknown metric '{metric}' for raw")
        rows = common.query_all(
            f"SELECT time, {metric} AS value FROM telemetry "
            "WHERE device_id = %s AND time >= %s ORDER BY time",
            (device_id, since),
        )
        source = "telemetry"
    elif bucket in BUCKET_VIEW:
        if metric not in AGG_METRICS:
            raise HTTPException(status_code=422, detail=f"metric '{metric}' not aggregated; use bucket=raw")
        view = BUCKET_VIEW[bucket]
        rows = common.query_all(
            f"SELECT bucket AS time, avg_{metric} AS value FROM {view} "
            "WHERE device_id = %s AND bucket >= %s ORDER BY bucket",
            (device_id, since),
        )
        source = view
    else:
        raise HTTPException(status_code=422, detail="bucket must be raw, 1m, or 1h")
    return {
        "device_id": device_id, "metric": metric, "bucket": bucket, "source": source,
        "hours": hours, "count": len(rows), "series": rows,
    }


@router.get("/retention")
def retention(_p=Depends(require_role(*READ_ROLES))):
    """Introspect Historian storage: hypertable, continuous aggregates, and the
    compression/retention/refresh policy jobs (from sql/010_data_lifecycle.sql)."""
    out = {"hypertables": [], "continuous_aggregates": [], "policies": []}
    try:
        out["hypertables"] = common.query_all(
            "SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables")
    except Exception:  # noqa: BLE001
        pass
    try:
        out["continuous_aggregates"] = common.query_all(
            "SELECT view_name, materialization_hypertable_name "
            "FROM timescaledb_information.continuous_aggregates")
    except Exception:  # noqa: BLE001
        pass
    try:
        # %% — common.query_all passes params, so psycopg2 treats a literal % as a
        # placeholder; escape it. (Silent failure here previously returned [].)
        out["policies"] = common.query_all(
            "SELECT proc_name, schedule_interval::text, config "
            "FROM timescaledb_information.jobs WHERE proc_name LIKE 'policy%%'")
    except Exception:  # noqa: BLE001
        pass
    return out
