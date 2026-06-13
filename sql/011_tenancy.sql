-- Phase 12 — multi-tenancy. Additive: existing devices fall into the 'default'
-- tenant; tenant-scoped principals only see their own devices, global principals
-- (admin/service) see all.

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    plan        VARCHAR(30) NOT NULL DEFAULT 'standard',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tenants (tenant_id, name, plan) VALUES
    ('default', 'Default Tenant', 'standard'),
    ('acme',    'Acme Energy',    'enterprise'),
    ('globex',  'Globex Utility', 'standard')
ON CONFLICT (tenant_id) DO NOTHING;

ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(50) NOT NULL DEFAULT 'default'
        REFERENCES tenants(tenant_id);

CREATE INDEX IF NOT EXISTS devices_tenant_idx ON devices(tenant_id);
