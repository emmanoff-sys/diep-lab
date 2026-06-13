-- Register the microgrid controller. device_type 'microgrid' must match the
-- ALLOWED_COMMANDS key in fastapi/app.py and the domainMap in the Node-RED
-- command router (microgrid -> microgrid).

INSERT INTO devices (device_id, device_type, location, status)
VALUES ('MG001', 'microgrid', 'Abuja Site A', 'ONLINE')
ON CONFLICT (device_id) DO NOTHING;

-- Populate the (previously empty) sites table with the microgrid's site.
INSERT INTO sites (site_name, site_type, latitude, longitude)
VALUES ('Abuja Site A', 'microgrid', 9.0765, 7.3986)
ON CONFLICT DO NOTHING;
