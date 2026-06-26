-- Removes the SIT-* synthetic fixtures registered by 00_fixtures.sql.
-- NOT run by default this sprint -- SYSTEM_ACCEPTANCE_REPORT.md's decision
-- was to leave them in place (clearly SIT-prefixed, harmless, and useful
-- for any follow-up re-validation after the report's recommendations are
-- addressed). Run manually if/when cleanup is wanted.

DELETE FROM grid_nodes WHERE node_id LIKE 'SIT-%';
DELETE FROM devices WHERE device_id LIKE 'SIT-%';
DELETE FROM tenants WHERE tenant_id IN ('sit-tenant', 'sit-tenant-b');
DELETE FROM sites WHERE site_name = 'SIT Validation Site';
-- telemetry rows are intentionally left (they're the evidence this sprint's
-- reports cite) -- delete manually with a WHERE device_id LIKE 'SIT-%' if
-- ever needed; not included here so this script can't accidentally erase
-- evidence.
