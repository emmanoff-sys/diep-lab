-- Backfill devices.site_name for the DIEP pilot fleet.
--
-- Context: SITE_NAME_AUDIT_REPORT.md (2026-06-15) — all 5 devices have
-- site_name IS NULL, but devices.location and the sole row in `sites`
-- both agree on 'Abuja Site A'. This satisfies the
-- devices_site_name_fkey -> sites(site_name) constraint.
--
-- Usage:
--   docker exec -i diep-timescaledb psql -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/sql/site_name_backfill.sql

BEGIN;

-- Before: confirm the rows this migration will touch.
SELECT device_id, device_type, site_name, location, status
FROM devices
WHERE site_name IS NULL
ORDER BY device_id;

SELECT
    count(*) AS total,
    count(*) FILTER (WHERE site_name IS NULL) AS null_site,
    count(*) FILTER (WHERE site_name = '') AS empty_site
FROM devices;

UPDATE devices
SET site_name = 'Abuja Site A'
WHERE site_name IS NULL;

-- After: verify every device now has a site_name and the FK resolves.
SELECT device_id, device_type, site_name, location, status
FROM devices
ORDER BY device_id;

SELECT
    count(*) AS total,
    count(*) FILTER (WHERE site_name IS NULL) AS null_site,
    count(*) FILTER (WHERE site_name = '') AS empty_site
FROM devices;

COMMIT;
