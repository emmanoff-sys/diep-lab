-- Phase 9-Data — telemetry lifecycle: downsampling (continuous aggregates),
-- native compression, and retention. All additive; retention/compression windows
-- are set so nothing current is dropped or compressed yet (data is only days old).

-- 1-minute rollup (recent dashboards / fine-grained trends).
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1m
WITH (timescaledb.continuous) AS
SELECT device_id,
       time_bucket('1 minute', time) AS bucket,
       avg(power_kw)     AS avg_power_kw,
       max(power_kw)     AS max_power_kw,
       min(power_kw)     AS min_power_kw,
       avg(voltage)      AS avg_voltage,
       avg(frequency)    AS avg_frequency,
       avg(solar_kw)     AS avg_solar_kw,
       avg(battery_soc)  AS avg_battery_soc,
       avg(temperature)  AS avg_temperature,
       avg(power_factor) AS avg_power_factor,
       count(*)          AS samples
FROM telemetry
GROUP BY device_id, bucket
WITH NO DATA;

-- 1-hour rollup (long-term trends; kept long, raw dropped sooner).
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1h
WITH (timescaledb.continuous) AS
SELECT device_id,
       time_bucket('1 hour', time) AS bucket,
       avg(power_kw)     AS avg_power_kw,
       max(power_kw)     AS max_power_kw,
       min(power_kw)     AS min_power_kw,
       avg(voltage)      AS avg_voltage,
       avg(frequency)    AS avg_frequency,
       avg(solar_kw)     AS avg_solar_kw,
       avg(battery_soc)  AS avg_battery_soc,
       avg(temperature)  AS avg_temperature,
       avg(power_factor) AS avg_power_factor,
       count(*)          AS samples
FROM telemetry
GROUP BY device_id, bucket
WITH NO DATA;

-- Refresh policies keep the aggregates current automatically.
SELECT add_continuous_aggregate_policy('telemetry_1m',
    start_offset => INTERVAL '2 hours', end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes', if_not_exists => true);

SELECT add_continuous_aggregate_policy('telemetry_1h',
    start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour', if_not_exists => true);

-- Native columnar compression on raw telemetry chunks older than 7 days.
ALTER TABLE telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => true);

-- Retention: drop raw telemetry older than 90 days (aggregates persist).
-- Tune down (e.g. 7-30 days) in production once the rollups are trusted.
SELECT add_retention_policy('telemetry', INTERVAL '90 days', if_not_exists => true);
SELECT add_retention_policy('telemetry_1m', INTERVAL '180 days', if_not_exists => true);
