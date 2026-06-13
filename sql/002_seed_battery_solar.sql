-- Register the battery and solar-inverter assets used by the new simulators.
-- device_type values MUST match ALLOWED_COMMANDS keys in fastapi/app.py and the
-- domainMap in the Node-RED command router (battery->battery, solar_inverter->solar).

INSERT INTO devices (device_id, device_type, location, status) VALUES
    ('BAT001', 'battery',        'Abuja Site A', 'ONLINE'),
    ('INV001', 'solar_inverter', 'Abuja Site A', 'ONLINE')
ON CONFLICT (device_id) DO NOTHING;

INSERT INTO battery_assets (asset_id, capacity_kwh, soc, status)
VALUES ('BAT001', 100, 50, 'IDLE')
ON CONFLICT (asset_id) DO NOTHING;

INSERT INTO solar_assets (asset_id, site_name, capacity_kw, status)
VALUES ('INV001', 'Abuja Site A', 10, 'ONLINE')
ON CONFLICT (asset_id) DO NOTHING;
