-- DIEP ADMS M1 — Unified Network Model (canonical grid topology).
--
-- Single source of truth for grid connectivity that all ADMS modules read from
-- (OMS affected-customer lookup, DMS state-estimation/FLISR graph walk, DERMS
-- node binding) instead of re-deriving structure from the flat devices table.
--
-- Design: a generic directed graph — grid_nodes (substation|feeder|transformer|
-- switch|bus|meter|der|load) + grid_edges (line|switch|transformer|tie) — rather
-- than one rigid table per asset class, so graph queries (downstream, path) and
-- FLISR switching are uniform. Physical assets link back to devices(device_id)
-- via grid_nodes.device_id, so live telemetry/Redis state joins onto topology.
--
-- Versioned: network_model_versions records each published model; nodes/edges
-- carry model_version so a future re-publish can be diffed/rolled back. Additive
-- and idempotent (IF NOT EXISTS / ON CONFLICT DO NOTHING), matching sql/000..012.

-- --- model version registry --------------------------------------------------
CREATE TABLE IF NOT EXISTS network_model_versions (
    version      BIGSERIAL PRIMARY KEY,
    label        VARCHAR(100) NOT NULL,
    description  TEXT,
    created_by   VARCHAR(100) NOT NULL DEFAULT 'system',
    is_current   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO network_model_versions (version, label, description, is_current)
VALUES (1, 'initial', 'Pilot Abuja Site A network model seeded with ADMS M1', TRUE)
ON CONFLICT (version) DO NOTHING;

-- --- nodes -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grid_nodes (
    node_id        VARCHAR(64) PRIMARY KEY,
    node_type      VARCHAR(32) NOT NULL
        CHECK (node_type IN ('substation','feeder','transformer','switch','bus','meter','der','load')),
    name           VARCHAR(128),
    parent_id      VARCHAR(64) REFERENCES grid_nodes(node_id),
    site_name      VARCHAR(100) REFERENCES sites(site_name),
    device_id      VARCHAR(50) REFERENCES devices(device_id),  -- nullable: links a node to a live asset
    latitude       NUMERIC(9,6),
    longitude      NUMERIC(9,6),
    nominal_kv     REAL,
    attrs          JSONB NOT NULL DEFAULT '{}'::jsonb,
    tenant_id      VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    model_version  BIGINT REFERENCES network_model_versions(version),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS grid_nodes_type_idx   ON grid_nodes(node_type);
CREATE INDEX IF NOT EXISTS grid_nodes_parent_idx ON grid_nodes(parent_id);
CREATE INDEX IF NOT EXISTS grid_nodes_device_idx ON grid_nodes(device_id);
CREATE INDEX IF NOT EXISTS grid_nodes_site_idx   ON grid_nodes(site_name);
CREATE INDEX IF NOT EXISTS grid_nodes_tenant_idx ON grid_nodes(tenant_id);

-- --- edges (electrical connectivity; switchable edges carry live state) -------
CREATE TABLE IF NOT EXISTS grid_edges (
    edge_id         VARCHAR(64) PRIMARY KEY,
    from_node       VARCHAR(64) NOT NULL REFERENCES grid_nodes(node_id),
    to_node         VARCHAR(64) NOT NULL REFERENCES grid_nodes(node_id),
    edge_type       VARCHAR(32) NOT NULL DEFAULT 'line'
        CHECK (edge_type IN ('line','switch','transformer','tie')),
    is_switchable   BOOLEAN NOT NULL DEFAULT FALSE,
    normally_closed BOOLEAN NOT NULL DEFAULT TRUE,
    is_closed       BOOLEAN NOT NULL DEFAULT TRUE,   -- live state; FLISR (DMS) mutates this
    rating_kw       REAL,
    attrs           JSONB NOT NULL DEFAULT '{}'::jsonb,
    tenant_id       VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    model_version   BIGINT REFERENCES network_model_versions(version),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS grid_edges_from_idx ON grid_edges(from_node);
CREATE INDEX IF NOT EXISTS grid_edges_to_idx   ON grid_edges(to_node);

-- --- customers + service points (meter <-> customer <-> node) for OMS ---------
CREATE TABLE IF NOT EXISTS customers (
    customer_id  VARCHAR(64) PRIMARY KEY,
    name         VARCHAR(128),
    address      VARCHAR(256),
    phone        VARCHAR(40),
    priority     VARCHAR(16) NOT NULL DEFAULT 'standard'
        CHECK (priority IN ('standard','medical','critical')),
    tenant_id    VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_points (
    service_point_id VARCHAR(64) PRIMARY KEY,
    customer_id      VARCHAR(64) REFERENCES customers(customer_id),
    node_id          VARCHAR(64) REFERENCES grid_nodes(node_id),
    meter_device_id  VARCHAR(50) REFERENCES devices(device_id),
    tenant_id        VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS service_points_node_idx     ON service_points(node_id);
CREATE INDEX IF NOT EXISTS service_points_meter_idx    ON service_points(meter_device_id);
CREATE INDEX IF NOT EXISTS service_points_customer_idx ON service_points(customer_id);

-- --- seed: pilot Abuja Site A network -----------------------------------------
-- Topology:  SUB-ABUJA -[line]-> FDR-01 -[switch SW-01]-> TX-01 -[xfmr]-> BUS-01
--            BUS-01 fans out to the meter node and the four DER/asset nodes.
-- SW-01 is the sectionalizing switch FLISR operates; opening it de-energises
-- everything downstream of TX-01 (the whole LV bus), which OMS reports as the
-- affected-customer set.
INSERT INTO grid_nodes (node_id, node_type, name, parent_id, site_name, device_id, latitude, longitude, nominal_kv, model_version) VALUES
    ('SUB-ABUJA',  'substation',  'Abuja Substation',        NULL,        'Abuja Site A', NULL,       9.0765, 7.3986, 33.0, 1),
    ('FDR-01',     'feeder',      'Feeder 01',               'SUB-ABUJA', 'Abuja Site A', NULL,       9.0768, 7.3990, 11.0, 1),
    ('TX-01',      'transformer', 'Distribution TX 01',      'FDR-01',    'Abuja Site A', NULL,       9.0770, 7.3994, 0.415, 1),
    ('BUS-01',     'bus',         'LV Bus 01',               'TX-01',     'Abuja Site A', NULL,       9.0771, 7.3995, 0.415, 1),
    ('ND-METER001','meter',       'Meter METER001',          'BUS-01',    'Abuja Site A', 'METER001', 9.0772, 7.3996, 0.415, 1),
    ('ND-BAT001',  'der',         'Battery BAT001',          'BUS-01',    'Abuja Site A', 'BAT001',   9.0773, 7.3997, 0.415, 1),
    ('ND-INV001',  'der',         'Solar Inverter INV001',   'BUS-01',    'Abuja Site A', 'INV001',   9.0774, 7.3998, 0.415, 1),
    ('ND-EV001',   'load',        'EV Charger EV001',        'BUS-01',    'Abuja Site A', 'EV001',    9.0775, 7.3999, 0.415, 1),
    ('ND-MG001',   'der',         'Microgrid Controller MG001','BUS-01',  'Abuja Site A', 'MG001',    9.0776, 7.4000, 0.415, 1)
ON CONFLICT (node_id) DO NOTHING;

INSERT INTO grid_edges (edge_id, from_node, to_node, edge_type, is_switchable, normally_closed, is_closed, rating_kw, model_version) VALUES
    ('E-SUB-FDR',   'SUB-ABUJA', 'FDR-01',      'line',        FALSE, TRUE, TRUE, 5000, 1),
    ('E-SW-01',     'FDR-01',    'TX-01',       'switch',      TRUE,  TRUE, TRUE, 2000, 1),
    ('E-TX-BUS',    'TX-01',     'BUS-01',      'transformer', FALSE, TRUE, TRUE, 1000, 1),
    ('E-BUS-METER', 'BUS-01',    'ND-METER001', 'line',        FALSE, TRUE, TRUE,  100, 1),
    ('E-BUS-BAT',   'BUS-01',    'ND-BAT001',   'line',        FALSE, TRUE, TRUE,  200, 1),
    ('E-BUS-INV',   'BUS-01',    'ND-INV001',   'line',        FALSE, TRUE, TRUE,  100, 1),
    ('E-BUS-EV',    'BUS-01',    'ND-EV001',    'line',        FALSE, TRUE, TRUE,   50, 1),
    ('E-BUS-MG',    'BUS-01',    'ND-MG001',    'line',        FALSE, TRUE, TRUE,  500, 1)
ON CONFLICT (edge_id) DO NOTHING;

INSERT INTO customers (customer_id, name, address, phone, priority) VALUES
    ('CUST-001', 'Abuja General Hospital', '1 Hospital Rd, Abuja', '+234-800-0001', 'medical'),
    ('CUST-002', 'Central Market',         '5 Market Sq, Abuja',   '+234-800-0002', 'standard'),
    ('CUST-003', 'Residential Block C',    '12 Unity Ave, Abuja',  '+234-800-0003', 'standard')
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO service_points (service_point_id, customer_id, node_id, meter_device_id) VALUES
    ('SP-001', 'CUST-001', 'ND-METER001', 'METER001'),
    ('SP-002', 'CUST-002', 'ND-METER001', 'METER001'),
    ('SP-003', 'CUST-003', 'ND-METER001', 'METER001')
ON CONFLICT (service_point_id) DO NOTHING;
