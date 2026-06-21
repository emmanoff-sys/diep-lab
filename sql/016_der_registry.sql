-- DIEP ADMS M4 — DERMS layer: formal DER asset registry.
--
-- Unifies the existing battery/solar/EV assets into one Distributed Energy
-- Resource registry, bound to the M1 network model (grid_nodes) and grouped for
-- VPP-style aggregation. Dispatch/curtailment reuse the existing command path
-- (fastapi _dispatch_command -> Kafka diep.commands -> dispatcher -> MQTT), so
-- this adds a registry + aggregation layer, not a new control plane.
--
-- Additive + idempotent, matching sql/000..015.

CREATE TABLE IF NOT EXISTS der_assets (
    der_id        VARCHAR(50) PRIMARY KEY REFERENCES devices(device_id),
    der_type      VARCHAR(32) NOT NULL CHECK (der_type IN ('battery','solar','ev_charger','microgrid')),
    node_id       VARCHAR(64) REFERENCES grid_nodes(node_id),
    rated_kw      REAL,                 -- max real-power capability
    rated_kwh     REAL,                 -- storage energy capacity (battery only)
    controllable  BOOLEAN NOT NULL DEFAULT TRUE,
    vpp_group     VARCHAR(64),          -- aggregation group (virtual power plant)
    tenant_id     VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS der_assets_type_idx  ON der_assets(der_type);
CREATE INDEX IF NOT EXISTS der_assets_node_idx  ON der_assets(node_id);
CREATE INDEX IF NOT EXISTS der_assets_group_idx ON der_assets(vpp_group);

-- Seed the pilot DER fleet from the existing devices, bound to their grid nodes.
INSERT INTO der_assets (der_id, der_type, node_id, rated_kw, rated_kwh, controllable, vpp_group) VALUES
    ('BAT001', 'battery',    'ND-BAT001', 50.0, 100.0, TRUE, 'abuja-vpp'),
    ('INV001', 'solar',      'ND-INV001', 10.0, NULL,  TRUE, 'abuja-vpp'),
    ('EV001',  'ev_charger', 'ND-EV001',  22.0, NULL,  TRUE, 'abuja-vpp'),
    ('MG001',  'microgrid',  'ND-MG001',  500.0, NULL, TRUE, 'abuja-vpp')
ON CONFLICT (der_id) DO NOTHING;
