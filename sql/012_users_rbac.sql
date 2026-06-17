-- DIEP Phase 21 — portal authentication/RBAC + audit correlation.
--
-- Adds a DB-backed, runtime-mutable user store (auth.py seeds it from the
-- existing env-derived USERS map on first use) so login passwords can be
-- changed at runtime (logout-everywhere / password reset), and a 4th role,
-- 'engineer', alongside the existing viewer/operator/admin/service tiers.
--
-- Also extends audit_events (additive, nullable columns — no existing row or
-- query shape changes) with per-request correlation and site attribution.

CREATE TABLE IF NOT EXISTS portal_users (
    username              VARCHAR(100) PRIMARY KEY,
    password_hash         VARCHAR(255) NOT NULL,
    role                  VARCHAR(20) NOT NULL CHECK (role IN ('viewer', 'operator', 'engineer', 'admin')),
    tenant                VARCHAR(100),
    token_version         INTEGER NOT NULL DEFAULT 0,
    must_change_password  BOOLEAN NOT NULL DEFAULT false,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS site VARCHAR(100),
    ADD COLUMN IF NOT EXISTS request_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS audit_events_site_idx ON audit_events(site);
CREATE INDEX IF NOT EXISTS audit_events_request_id_idx ON audit_events(request_id);
