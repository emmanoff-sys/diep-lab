-- Register the smart meter device used by the telemetry pipeline.
INSERT INTO devices (device_id, device_type, location, status)
VALUES ('METER001', 'smartmeter', 'Abuja Site A', 'ONLINE')
ON CONFLICT (device_id) DO NOTHING;
