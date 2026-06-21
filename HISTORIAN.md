# DIEP Historian

The **Historian** is DIEP's time-series store of record: the TimescaleDB
`telemetry` hypertable plus its continuous aggregates and lifecycle policies,
exposed through a documented query API (ADMS M5a). It is not new infrastructure —
it formalizes what `sql/000_schema.sql`, `sql/009_schema_extension.sql`, and
`sql/010_data_lifecycle.sql` already provision.

## Storage model

| Object | Type | Purpose |
|--------|------|---------|
| `telemetry` | hypertable (partitioned on `time`) | raw device readings (8 canonical + typed columns + `metadata` JSONB) |
| `telemetry_1m` | continuous aggregate | 1-minute rollups: `avg/max/min_power_kw`, `avg_voltage`, `avg_frequency`, `avg_solar_kw`, `avg_battery_soc`, `avg_temperature`, `avg_power_factor`, `samples` |
| `telemetry_1h` | continuous aggregate | 1-hour rollups (same columns) |

## Lifecycle policies (`sql/010_data_lifecycle.sql`)

| Policy | Setting |
|--------|---------|
| Compression | compress chunks older than **7 days** |
| Raw retention | drop `telemetry` chunks after **90 days** |
| `telemetry_1m` retention | **180 days** |
| `telemetry_1h` retention | indefinite |
| Cagg refresh | `telemetry_1m` every 5 min; `telemetry_1h` hourly |

Inspect them live: `GET /historian/retention`.

## Query API

### `GET /historian/query`
| Param | Default | Notes |
|-------|---------|-------|
| `device_id` | (required) | |
| `metric` | `power_kw` | raw: power_kw, voltage, current, frequency, solar_kw, battery_soc, grid_import_kw, grid_export_kw, temperature, power_factor; aggregated subset excludes current/grid_* |
| `bucket` | `raw` | `raw` → hypertable; `1m`/`1h` → continuous aggregate (`avg_<metric>`) |
| `hours` | `24` | lookback window |

Returns `{device_id, metric, bucket, source, count, series:[{time, value}]}`.
Metric names are whitelisted (the column is interpolated), guarding injection.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://diep-fastapi:8000/historian/query?device_id=BAT001&metric=power_kw&bucket=1h&hours=168"
```

### `GET /historian/retention`
Returns the hypertable(s), continuous aggregates, and the compression/retention/
refresh policy jobs (with their `config`) — a live view of the lifecycle above.

## Forecasting (M5b)

`GET /forecast/load?device_id=&horizon_hours=&history_hours=` returns a
short-term `power_kw` forecast built on Historian data: an hour-of-day seasonal
mean blended with a recent moving average when ≥ ~1 day of history exists, else a
flat moving-average projection. Lightweight by design (pure stdlib, no ML deps);
shown on the portal **Load Forecasting** tab.
