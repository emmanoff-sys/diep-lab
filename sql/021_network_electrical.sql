-- DIEP ADMS P5-M1 — Network Model Service: electrical parameters.
--
-- The M1 model (sql/013) captured *connectivity* (nodes/edges) — enough for OMS
-- affected-customer walks and FLISR switching. P5 turns DIEP into a utility-grade
-- ADMS: distribution state estimation (P5-M2) and three-phase power flow (P5-M3)
-- need the *electrical* model — series impedance, ampacity, phasing, and per-node
-- base load. This migration adds those attributes to the existing tables and
-- seeds realistic values for the Abuja Site A pilot feeder. No new tables, no
-- topology change: purely additive columns + UPDATEs, idempotent (matching
-- sql/000..020). Existing connectivity queries (OMS/FLISR/DERMS) are untouched.
--
-- Modeling notes
--   * Impedance is stored in ohms referred to the *downstream* node's voltage
--     base. The power-flow solver (P5-M3) converts to per-unit on each node's own
--     nominal_kv, so an element spanning two voltage levels (a transformer, or the
--     33->11 kV head) is handled by the nodes' differing nominal_kv — no special
--     ratio column needed.
--   * `phases` follows utility convention: 'ABC' three-phase, 'A'/'B'/'C' single-
--     phase laterals, 'AB'/etc. two-phase. The EV charger is modeled single-phase
--     on A so the pilot exercises genuine unbalance (mission requirement).
--   * Transformer thermal limit reuses the existing grid_edges.rating_kw (kVA);
--     lines use the new ampacity_a.

-- --- recloser as a first-class node type -------------------------------------
-- Reclosers/sectionalizers are normally modeled as switchable edges (edge_type
-- 'switch' with attrs.role), but we widen the node-type vocabulary so a recloser
-- can also be a named device node when a utility models it that way. The inline
-- CHECK from sql/013 is auto-named grid_nodes_node_type_check.
ALTER TABLE grid_nodes DROP CONSTRAINT IF EXISTS grid_nodes_node_type_check;
ALTER TABLE grid_nodes ADD CONSTRAINT grid_nodes_node_type_check
    CHECK (node_type IN ('substation','feeder','transformer','switch','recloser',
                         'bus','meter','der','load'));

-- --- per-node electrical attributes ------------------------------------------
ALTER TABLE grid_nodes ADD COLUMN IF NOT EXISTS phases         VARCHAR(3)  NOT NULL DEFAULT 'ABC';
ALTER TABLE grid_nodes ADD COLUMN IF NOT EXISTS base_load_kw   REAL        NOT NULL DEFAULT 0;
ALTER TABLE grid_nodes ADD COLUMN IF NOT EXISTS base_load_kvar REAL        NOT NULL DEFAULT 0;
ALTER TABLE grid_nodes ADD COLUMN IF NOT EXISTS load_class     VARCHAR(32);

-- --- per-edge electrical attributes ------------------------------------------
ALTER TABLE grid_edges ADD COLUMN IF NOT EXISTS resistance_r_ohm REAL;
ALTER TABLE grid_edges ADD COLUMN IF NOT EXISTS reactance_x_ohm  REAL;
ALTER TABLE grid_edges ADD COLUMN IF NOT EXISTS length_km        REAL;
ALTER TABLE grid_edges ADD COLUMN IF NOT EXISTS ampacity_a       REAL;
ALTER TABLE grid_edges ADD COLUMN IF NOT EXISTS phases           VARCHAR(3) NOT NULL DEFAULT 'ABC';

-- --- seed: Abuja Site A electrical parameters --------------------------------
-- Nodes: phasing + base load. Only the meter (3 customers) and the single-phase
-- EV charger carry base load; DER/storage nodes inject via telemetry (P5-M2/M3).
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='source'      WHERE node_id='SUB-ABUJA';
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='bus'         WHERE node_id='FDR-01';
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='transformer' WHERE node_id IN ('TX-01','TX-02');
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='bus'         WHERE node_id='BUS-01';
UPDATE grid_nodes SET phases='ABC', base_load_kw=80,  base_load_kvar=25, load_class='residential' WHERE node_id='ND-METER001';
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='storage'     WHERE node_id='ND-BAT001';
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='generation'  WHERE node_id='ND-INV001';
UPDATE grid_nodes SET phases='A',   base_load_kw=7.2, base_load_kvar=0,  load_class='ev'          WHERE node_id='ND-EV001';
UPDATE grid_nodes SET phases='ABC', base_load_kw=0,   base_load_kvar=0,  load_class='microgrid'   WHERE node_id IN ('ND-MG001','ND-MGD900');

-- Edges: series R/X (ohms, downstream base), length, ampacity, phasing.
UPDATE grid_edges SET resistance_r_ohm=0.500,  reactance_x_ohm=0.600,  length_km=1.5,  ampacity_a=400,  phases='ABC' WHERE edge_id='E-SUB-FDR';
UPDATE grid_edges SET resistance_r_ohm=0.050,  reactance_x_ohm=0.020,  length_km=0.1,  ampacity_a=400,  phases='ABC' WHERE edge_id IN ('E-SW-01','E-SW-02');
UPDATE grid_edges SET resistance_r_ohm=0.0020, reactance_x_ohm=0.0084, length_km=0.0,  ampacity_a=1400, phases='ABC' WHERE edge_id='E-TX-BUS';
UPDATE grid_edges SET resistance_r_ohm=0.0030, reactance_x_ohm=0.0100, length_km=0.0,  ampacity_a=1400, phases='ABC' WHERE edge_id='E-TIE-01';
UPDATE grid_edges SET resistance_r_ohm=0.040,  reactance_x_ohm=0.015,  length_km=0.15, ampacity_a=200,  phases='ABC' WHERE edge_id='E-BUS-METER';
UPDATE grid_edges SET resistance_r_ohm=0.020,  reactance_x_ohm=0.008,  length_km=0.05, ampacity_a=300,  phases='ABC' WHERE edge_id='E-BUS-BAT';
UPDATE grid_edges SET resistance_r_ohm=0.030,  reactance_x_ohm=0.012,  length_km=0.08, ampacity_a=150,  phases='ABC' WHERE edge_id='E-BUS-INV';
UPDATE grid_edges SET resistance_r_ohm=0.050,  reactance_x_ohm=0.020,  length_km=0.10, ampacity_a=63,   phases='A'   WHERE edge_id='E-BUS-EV';
UPDATE grid_edges SET resistance_r_ohm=0.010,  reactance_x_ohm=0.005,  length_km=0.03, ampacity_a=800,  phases='ABC' WHERE edge_id='E-BUS-MG';
UPDATE grid_edges SET resistance_r_ohm=0.010,  reactance_x_ohm=0.005,  length_km=0.03, ampacity_a=400,  phases='ABC' WHERE edge_id='E-MGD900-CB';
