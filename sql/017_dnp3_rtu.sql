-- DIEP ADMS M7 — register the DNP3 (mock) RTU so docker-compose-dnp3.yml works
-- out of the box: the ingestor only accepts telemetry for known devices, and the
-- topology node binds the RTU into the M1 network model. Additive + idempotent.

INSERT INTO devices (device_id, device_type, location, status, site_name, tenant_id) VALUES
    ('MGD900', 'microgrid', 'Abuja Site A', 'ONLINE', 'Abuja Site A', 'default')
ON CONFLICT (device_id) DO NOTHING;

INSERT INTO grid_nodes (node_id, node_type, name, parent_id, site_name, device_id, nominal_kv, model_version) VALUES
    ('ND-MGD900', 'der', 'DNP3 RTU MGD900', 'BUS-01', 'Abuja Site A', 'MGD900', 0.415, 1)
ON CONFLICT (node_id) DO NOTHING;
