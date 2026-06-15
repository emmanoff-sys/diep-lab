-- Register the smart meter device used by the telemetry pipeline.
INSERT INTO devices (device_id, device_type, location, status, site_name)
VALUES ('METER001', 'smartmeter', 'Abuja Site A', 'ONLINE', 'Abuja Site A')
ON CONFLICT (device_id) DO NOTHING;
