-- Phase 9-Schema — extend canonical telemetry with the device-class fields the
-- Phase 9C–9G drivers already publish on MQTT but that were dropped at /telemetry.
-- All additive + nullable (safe on the existing hypertable; existing rows = NULL).
--
-- Typed columns for the broadly-useful, queryable metrics; the existing
-- telemetry.metadata JSONB carries the per-reading device-specific long tail
-- (vehicle_soc, connector_status, session_energy_kwh, load_kw, setpoint_kw,
--  grid_connected, mode, ...).

ALTER TABLE telemetry
    ADD COLUMN IF NOT EXISTS power_factor      double precision,  -- meters
    ADD COLUMN IF NOT EXISTS energy_import_kwh double precision,  -- meters
    ADD COLUMN IF NOT EXISTS energy_export_kwh double precision,  -- meters
    ADD COLUMN IF NOT EXISTS temperature       double precision,  -- battery / thermal (deg C)
    ADD COLUMN IF NOT EXISTS soh               double precision,  -- battery state of health (%)
    ADD COLUMN IF NOT EXISTS state             varchar(30);       -- device operating state
