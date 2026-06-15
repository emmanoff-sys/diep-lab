-- Register the microgrid controller. device_type 'microgrid' must match the
-- ALLOWED_COMMANDS key in fastapi/app.py and the domainMap in the Node-RED
-- command router (microgrid -> microgrid).

INSERT INTO devices (device_id, device_type, location, status, site_name)
VALUES ('MG001', 'microgrid', 'Abuja Site A', 'ONLINE', 'Abuja Site A')
ON CONFLICT (device_id) DO NOTHING;

-- The 'Abuja Site A' row in `sites` is seeded by sql/000_schema.sql (runs first,
-- before any devices.site_name FK references need it).
