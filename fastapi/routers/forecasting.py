"""ADMS M5b — short-term load forecasting (stub).

A lightweight moving-average + daily-seasonal forecaster over the Historian
(telemetry power_kw). No heavy ML deps (pure stdlib): builds an hour-of-day
seasonal profile when ≥~1 day of history exists, otherwise falls back to a flat
recent moving average. Exposed via API and shown on a portal panel.
"""
import statistics
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query

import common
from auth import require_role

router = APIRouter(prefix="/forecast", tags=["forecasting"])

READ_ROLES = ("viewer", "operator", "engineer", "admin", "service")


@router.get("/load")
def load_forecast(
    device_id: str = Query(..., examples=["BAT001"]),
    horizon_hours: int = Query(24, ge=1, le=168),
    history_hours: int = Query(168, ge=1, le=24 * 90),
    _p=Depends(require_role(*READ_ROLES)),
):
    """Forecast power_kw for the next horizon_hours from recent history.

    Method: hour-of-day seasonal mean blended with a recent moving average when
    the history spans ≥ ~1 day; otherwise a flat moving-average projection.
    """
    if common.query_one("SELECT 1 FROM devices WHERE device_id = %s", (device_id,)) is None:
        raise HTTPException(status_code=404, detail=f"unknown device '{device_id}'")

    since = datetime.now(timezone.utc) - timedelta(hours=history_hours)
    rows = common.query_all(
        "SELECT time, power_kw FROM telemetry "
        "WHERE device_id = %s AND time >= %s AND power_kw IS NOT NULL ORDER BY time",
        (device_id, since),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"no telemetry history for '{device_id}'")

    values = [float(r["power_kw"]) for r in rows]
    times = [r["time"] for r in rows]
    last_time = times[-1]

    # recent moving average (last up-to-20 points).
    recent = values[-20:]
    moving_avg = statistics.mean(recent)
    overall_mean = statistics.mean(values)

    # hour-of-day seasonal profile.
    span_hours = (times[-1] - times[0]).total_seconds() / 3600.0
    has_daily = span_hours >= 23
    seasonal: dict[int, float] = {}
    if has_daily:
        buckets: dict[int, list] = {}
        for t, v in zip(times, values):
            buckets.setdefault(t.hour, []).append(v)
        seasonal = {h: statistics.mean(vs) for h, vs in buckets.items()}

    method = "daily_seasonal+moving_avg" if has_daily else "moving_avg_flat"
    forecast = []
    for h in range(1, horizon_hours + 1):
        ft = last_time + timedelta(hours=h)
        if has_daily and ft.hour in seasonal:
            base = 0.6 * seasonal[ft.hour] + 0.4 * moving_avg
        else:
            base = moving_avg if has_daily else moving_avg
        forecast.append({"time": ft.isoformat(), "forecast_kw": round(max(0.0, base), 3)})

    return {
        "device_id": device_id,
        "method": method,
        "horizon_hours": horizon_hours,
        "history_points": len(values),
        "history_span_hours": round(span_hours, 2),
        "recent_moving_avg_kw": round(moving_avg, 3),
        "overall_mean_kw": round(overall_mean, 3),
        "forecast": forecast,
    }
