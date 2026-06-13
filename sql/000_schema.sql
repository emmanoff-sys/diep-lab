-- DIEP TimescaleDB schema and assets model
-- This file creates the device registry, asset tables, alarms, and telemetry hypertable.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS sites (
    site_name VARCHAR(100) PRIMARY KEY,
    site_type VARCHAR(50) NOT NULL,
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure legacy sites tables using integer PKs still expose site_name as a unique key.
ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS site_name VARCHAR(100);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relname = 'sites_site_name_idx'
           AND n.nspname = 'public'
    ) THEN
        CREATE UNIQUE INDEX sites_site_name_idx ON sites(site_name);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS devices (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL UNIQUE,
    device_type VARCHAR(50) NOT NULL,
    location VARCHAR(128),
    status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
    site_name VARCHAR(100) REFERENCES sites(site_name),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS site_name VARCHAR(100) REFERENCES sites(site_name);

CREATE TABLE IF NOT EXISTS solar_assets (
    asset_id VARCHAR(50) PRIMARY KEY REFERENCES devices(device_id),
    site_name VARCHAR(100) REFERENCES sites(site_name),
    capacity_kw REAL,
    status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS battery_assets (
    asset_id VARCHAR(50) PRIMARY KEY REFERENCES devices(device_id),
    capacity_kwh REAL,
    soc REAL,
    status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ev_chargers (
    charger_id VARCHAR(50) PRIMARY KEY REFERENCES devices(device_id),
    site_name VARCHAR(100) REFERENCES sites(site_name),
    status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
    max_power_kw REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alarms (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(50) REFERENCES devices(device_id),
    alarm_type VARCHAR(100),
    severity VARCHAR(50),
    message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    raised_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reconcile legacy alarms tables (older builds used alarm_message/created_at and
-- lacked metadata/raised_at). Additive only; the app queries message/metadata/raised_at.
ALTER TABLE alarms
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS raised_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS telemetry (
    time TIMESTAMPTZ NOT NULL DEFAULT now(),
    device_id VARCHAR(50) NOT NULL REFERENCES devices(device_id),
    voltage REAL,
    current REAL,
    power_kw REAL,
    frequency REAL,
    solar_kw REAL,
    battery_soc REAL,
    grid_import_kw REAL,
    grid_export_kw REAL,
    metadata JSONB DEFAULT '{}'::jsonb
);

SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);

ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS grid_import_kw REAL,
    ADD COLUMN IF NOT EXISTS grid_export_kw REAL,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS telemetry_device_id_idx ON telemetry(device_id);
CREATE INDEX IF NOT EXISTS telemetry_time_idx ON telemetry(time DESC);
