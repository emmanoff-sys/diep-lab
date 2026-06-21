-- DIEP ADMS M3 — Distribution Management System (DMS) basics.
--
-- 1) Adds network redundancy to the M1 pilot model so FLISR restoration is
--    meaningful: a backup transformer (TX-02) fed from a second switch, and a
--    NORMALLY-OPEN tie switch (E-TIE-01) that can back-feed BUS-01 when the
--    primary path (TX-01) is faulted/isolated.
-- 2) flisr_events — audit trail of fault-isolation-restoration runs.
--
-- Additive + idempotent, matching sql/000..014.

-- backup feed + tie (normally open) for FLISR
INSERT INTO grid_nodes (node_id, node_type, name, parent_id, site_name, device_id, latitude, longitude, nominal_kv, model_version) VALUES
    ('TX-02', 'transformer', 'Backup TX 02', 'FDR-01', 'Abuja Site A', NULL, 9.0769, 7.3992, 0.415, 1)
ON CONFLICT (node_id) DO NOTHING;

INSERT INTO grid_edges (edge_id, from_node, to_node, edge_type, is_switchable, normally_closed, is_closed, rating_kw, model_version) VALUES
    -- second sectionalizing switch feeding the backup transformer (normally closed, energized)
    ('E-SW-02',  'FDR-01', 'TX-02',  'switch', TRUE, TRUE,  TRUE,  2000, 1),
    -- normally-OPEN tie: TX-02 can back-feed BUS-01 when TX-01 is isolated
    ('E-TIE-01', 'TX-02',  'BUS-01', 'tie',    TRUE, FALSE, FALSE, 1000, 1)
ON CONFLICT (edge_id) DO NOTHING;

-- FLISR run audit
CREATE TABLE IF NOT EXISTS flisr_events (
    event_id      VARCHAR(64) PRIMARY KEY,          -- uuid4
    fault_node    VARCHAR(64) REFERENCES grid_nodes(node_id),
    fault_edge    VARCHAR(64),
    isolated_edges JSONB NOT NULL DEFAULT '[]'::jsonb,
    restored_edges JSONB NOT NULL DEFAULT '[]'::jsonb,
    customers_lost INT NOT NULL DEFAULT 0,
    customers_restored INT NOT NULL DEFAULT 0,
    executed      BOOLEAN NOT NULL DEFAULT FALSE,
    steps         JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS flisr_events_created_idx ON flisr_events(created_at DESC);
