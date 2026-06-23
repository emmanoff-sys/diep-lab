-- Phase 22 follow-on — persisted MW2 readiness verification results.
--
-- Additive only: stores scored readiness snapshots and their per-check detail
-- without touching any existing operational tables.

CREATE TABLE IF NOT EXISTS platform_readiness_reports (
    run_id          UUID PRIMARY KEY,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    score           INT NOT NULL CHECK (score >= 0 AND score <= 100),
    pass_threshold  INT NOT NULL CHECK (pass_threshold >= 0 AND pass_threshold <= 100),
    recommendation  TEXT NOT NULL,
    source          TEXT NOT NULL,
    tenant_id       VARCHAR(50) NOT NULL DEFAULT 'default' REFERENCES tenants(tenant_id),
    summary         JSONB NOT NULL DEFAULT '{}'::jsonb,
    checks          JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS platform_readiness_reports_checked_at_idx
    ON platform_readiness_reports (checked_at DESC);
CREATE INDEX IF NOT EXISTS platform_readiness_reports_status_idx
    ON platform_readiness_reports (status, checked_at DESC);
CREATE INDEX IF NOT EXISTS platform_readiness_reports_tenant_idx
    ON platform_readiness_reports (tenant_id, checked_at DESC);
