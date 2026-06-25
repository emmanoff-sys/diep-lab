-- DIEP System Integration Test (SIT) fixtures — System Integration Validation
-- sprint. Purely additive (ON CONFLICT DO NOTHING), same pattern as
-- sql/004_seed_smartmeter.sql. Registers 5 synthetic meters under a
-- dedicated SIT site and a feeder/transformer chain in grid_nodes, so
-- Deliverable 7 (topology validation) has real, non-synthetic-looking
-- enrichment to verify against — these are real grid_nodes rows, just for
-- test devices, not a fabricated enrichment result.
--
-- Cleanup: see validation/scripts/99_teardown_fixtures.sql (not run by
-- default — left in place so evidence/ rows remain queryable after the
-- sprint; see SYSTEM_ACCEPTANCE_REPORT.md for the decision).

INSERT INTO sites (site_name, site_type, latitude, longitude)
VALUES ('SIT Validation Site', 'test', 9.0765, 7.3986)
ON CONFLICT (site_name) DO NOTHING;

-- devices.tenant_id (added by sql/011_tenancy.sql) defaults to 'default' if
-- omitted — caught by Scenario A: MDM's device-registry enrichment legitimately
-- disagreed with the envelope's own self-reported tenant_id ("sit-tenant")
-- until this tenant row + explicit tenant_id existed. See
-- INTEGRATION_VALIDATION_REPORT.md Scenario A notes.
INSERT INTO tenants (tenant_id, name, plan)
VALUES ('sit-tenant', 'SIT Validation Tenant', 'internal')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO devices (device_id, device_type, location, status, site_name, tenant_id) VALUES
    ('SIT-METER-001', 'smartmeter', 'SIT Validation Site', 'ONLINE', 'SIT Validation Site', 'sit-tenant'),
    ('SIT-METER-002', 'smartmeter', 'SIT Validation Site', 'ONLINE', 'SIT Validation Site', 'sit-tenant'),
    ('SIT-METER-003', 'smartmeter', 'SIT Validation Site', 'ONLINE', 'SIT Validation Site', 'sit-tenant'),
    ('SIT-METER-004', 'smartmeter', 'SIT Validation Site', 'ONLINE', 'SIT Validation Site', 'sit-tenant'),
    ('SIT-METER-005', 'smartmeter', 'SIT Validation Site', 'ONLINE', 'SIT Validation Site', 'sit-tenant')
ON CONFLICT (device_id) DO NOTHING;

-- Scenario B (tenant isolation): a 6th meter under a SECOND tenant, so
-- cross-tenant data attribution can actually be tested.
INSERT INTO tenants (tenant_id, name, plan)
VALUES ('sit-tenant-b', 'SIT Validation Tenant B', 'internal')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO devices (device_id, device_type, location, status, site_name, tenant_id)
VALUES ('SIT-METER-006', 'smartmeter', 'SIT Validation Site', 'ONLINE', 'SIT Validation Site', 'sit-tenant-b')
ON CONFLICT (device_id) DO NOTHING;

INSERT INTO grid_nodes (node_id, node_type, name, parent_id, site_name, device_id, tenant_id) VALUES
    ('SIT-FDR-01', 'feeder', 'SIT Feeder 1', NULL, 'SIT Validation Site', NULL, 'sit-tenant'),
    ('SIT-TX-01', 'transformer', 'SIT Transformer 1', 'SIT-FDR-01', 'SIT Validation Site', NULL, 'sit-tenant'),
    ('SIT-NODE-METER-001', 'meter', 'SIT Meter 1 node', 'SIT-TX-01', 'SIT Validation Site', 'SIT-METER-001', 'sit-tenant'),
    ('SIT-NODE-METER-002', 'meter', 'SIT Meter 2 node', 'SIT-TX-01', 'SIT Validation Site', 'SIT-METER-002', 'sit-tenant'),
    ('SIT-NODE-METER-003', 'meter', 'SIT Meter 3 node', 'SIT-TX-01', 'SIT Validation Site', 'SIT-METER-003', 'sit-tenant'),
    ('SIT-NODE-METER-004', 'meter', 'SIT Meter 4 node', 'SIT-TX-01', 'SIT Validation Site', 'SIT-METER-004', 'sit-tenant'),
    ('SIT-NODE-METER-005', 'meter', 'SIT Meter 5 node', 'SIT-TX-01', 'SIT Validation Site', 'SIT-METER-005', 'sit-tenant'),
    ('SIT-NODE-METER-006', 'meter', 'SIT Meter 6 node', 'SIT-TX-01', 'SIT Validation Site', 'SIT-METER-006', 'sit-tenant-b')
ON CONFLICT (node_id) DO NOTHING;
